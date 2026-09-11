---
name: cargento
description: Open Cargento, a local agent-cartography dashboard for Claude Code, Codex, Pi, Gemini, Antigravity, Copilot, OpenCode, Cursor, Goose, and Droid sessions, with subagents, task progress, token rate, ETAs, and Claude input-wait notifications. Use for “open cargento” or “monitor agent progress”.
license: Apache-2.0 AND OFL-1.1
---

# Cargento

Cargento is an agnostic agent cartography and visualization tool: a local web dashboard mapping live coding-agent activity across **ten harnesses** on this machine — Claude Code, Codex, Pi, Gemini CLI, Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI, Goose, Factory Droid — each row badged with its harness. A "Discovered harnesses" strip at the top shows all supported harnesses; ones with local session data are green/enabled, others gray/disabled. A harness's sessions only appear if its data is discovered. Transcript-backed sessions appear even if they never called TaskCreate; Claude task files may also surface a task-only session when its transcript is unavailable. Per session: a live state badge, what it's doing right now, running subagents (named pills), a current-turn elapsed/ETA estimate with progress bar, a ⚠️ warning (with tooltip) when a request runs or is estimated ≥15 min, one row per tracked task, and the recent token output rate. Fires desktop notifications when a session is blocked waiting on the human — Claude, Codex, Copilot and Cursor are the four harnesses that can report that — and when any session registers a question through the ask lane. Sessions, Projects and Attention render the same data three ways — see Dashboard views below.

Store locations are resolved per platform, and the documented relocation variables are honored: `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME` (the CLI creates `.gemini` inside it; relocates the Antigravity store with it), `COPILOT_HOME`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR`. When one is set it is authoritative — no fallback to the default location. Run `--diagnose` to see every path searched.

Data sources (read-only, no external calls by default; the observer model is the one path that can send session content off this machine through the installed Codex CLI, off unless `--observer-model` is enabled and its disclosure is accepted; `--no-observer-model` refuses it for the run; all parsing is defensive — a broken harness store is skipped, never fatal):
- `~/.claude/projects/*/<session>.jsonl` — Claude transcript tails: session discovery, titles, token usage, pending AskUserQuestion detection and the text of the question it is asking
- Claude subagents, two generations: modern harnesses write each subagent as a top-level `~/.claude/projects/*/<uuid>.jsonl` whose records carry `agentName` + `teamName: "session-<parent prefix>"` — these fold into the parent session (named pill, its own start and elapsed, freshness, output rate) and never appear as standalone sessions. A teammate dispatched into its own pane stays on that row once it goes quiet, marked as no longer running rather than dropped, and its own subagents are walked and listed beside it, each attributed to the teammate that spawned it; legacy `<session-uuid>/subagents/agent-*.jsonl` + `.meta.json` files are still recognized (fresh mtime = running, and one the lead ran itself stays listed as no longer running once quiet, on the same display window as a teammate), including the `subagents/workflows/<run-id>/` directory a workflow fan-out nests its agents in. A bare `agentName` from a top-level `--agent` launch has no parent relation and remains a standalone session; `agentSetting`, not `agentName`, supplies any Spacedock role. Agent writes count as parent activity in their own right, so a session parked on a long background workflow reads Working rather than Idle
- Spacedock workflows: a Claude session launched by Spacedock carries an `agentSetting` of `spacedock:first-officer` or `spacedock:ensign` in its first transcript records, which is how its role badge appears. Pi writes no such setting, so a Pi session earns a first-officer badge from the boot envelope described below instead, and never an ensign one. A first officer also records its `spacedock status --boot` output — counted only when it arrives as command output, never as ordinary conversation text — which names each workflow directory and each entity-state directory absolutely. The ordered stage list comes from the workflow `README.md` frontmatter, and each entity's current stage from the `status` in its own state-file frontmatter; boot's `dispatchable` list is only a snapshot of what was ready to move at boot, so it fills in behind the state directory rather than standing in for it. Those two kinds of frontmatter are the only project files the stage-strip reader reads; the cockpit's separate project-context prototype also reads bounded dispatch and workflow evidence — see the repository's SECURITY.md for the contract, and `--no-spacedock` to disable it
- `~/.claude/teams/session-<id>/config.json` — the Claude teams registry: the roster of members a lead session has dispatched. A member is listed here the moment it is spawned, which is before it has written a transcript byte, so a member on the roster with no transcript anywhere is one that has not started — the shape an agent parked on a startup permission prompt takes on disk — and the session reports Needs input and names it. The roster is a roster and not a heartbeat: one file stamp covers every member and moves only on a join or a leave, so a member is read this way only once it has been registered longer than a healthy agent takes to start and only while the session is still inside the display window; running subagents keep their own transcript freshness. Older harnesses pruned a member as it finished; Claude Code 2.1.259 keeps it and marks it `isActive: false` instead, so what stops finished work from reading as running is transcript freshness, and that flag is only ever allowed to confirm a member has stopped, never to claim one is still going. A session directory with no `config.json` (an older layout) is skipped rather than treated as broken. A gate that opens mid-run is not detected: nothing in the store distinguishes a blocked member from a busy one once it has started
- `~/.claude/tasks/<session-id>/N.json` — tracked task state (subject, status, activeForm); current bare-UUID and older `session-<id>` directories are supported
- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — Codex. The newest instruction, the title and the agent's turn-start statement of intent come from a walk backward from the end of the file rather than from its tail, because Codex pads a rollout with large encrypted reasoning blobs and the prompt is usually well outside any bounded tail read. Line 1 (`session_meta`) gives identity + cwd; `thread_source: "subagent"` files are subagent threads (named by `agent_nickname`), grouped through `source.subagent.thread_spawn.parent_thread_id`; resumes dedupe to newest file per session. Codex's own plan is read from the newest `update_plan` record and becomes that session's task rows — the same backward walk and for the same reason, since a session that has done any work since writing its plan has pushed it out of tail range. Two wire shapes are read, because a given Codex build writes one or the other: an older tool call whose arguments are JSON, and the current one that carries the plan as JavaScript source. The walk does not stop at a compaction boundary the way the prompt walk does, since the CLI keeps showing the plan across one. A step carries no timestamps of its own, so a Codex session gets task rows and a progress count but no age per row and no "est. remaining"
- `~/.pi/agent/sessions/--<encoded-cwd>--/<timestamp>_<uuid>.jsonl` — Pi v3. The default store is nested; a custom session store is flat and contains JSONL files directly. The last persisted leaf's ancestor path is active, so sibling branches are excluded from prompts, tools, output usage, and turns. The latest global `session_info` name is the title, including a later clear; `parentSession` means fork or clone, never a subagent. Assistant, tool-result, compaction, and branch-summary output usage feed the rate. Pi has no allowance of its own, so each row also names the authority it is spending, read from the newest entry on the active branch that carries one (an assistant message, or a `model_change` the user has switched to but not spent yet): it renders as `via Codex · gpt-5.6-sol`, and a provider with no harness of its own keeps its own name. A session that names no provider makes no claim rather than guessing from Pi's current default. Pi has no passive needs-input or core-subagent signal. Its Working/Idle reading comes off the active-branch leaf record's `stopReason` rather than recency alone, and it is the only harness whose store records how a turn ended: an assistant leaf stamped `toolUse` is a tool call whose result has not been written, so it reads Working — `running <tool>` — past the 90s window and up to 15 minutes, because recency cannot tell a long `bash` from a parked session; past that it reads Idle, because a transcript can record that a tool started and can never record that the process died, so a Pi hard-killed mid-tool would otherwise hold the top of the board for the whole display window. A finished turn (`stop`, `aborted` or `error`) reads Idle the second it lands however fresh it is. A `user` or `toolResult` leaf has handed the turn back to the model and reads `thinking` while fresh. An unrecognised `stopReason` claims nothing and stays on recency. None of this distinguishes a finished turn from an unanswered wait, which still needs a turn-end event reaching the board: Pi documents `turn_end` and `agent_settled`, the second one for status integrations by name, but both are handed to an in-process extension handler and Cargento ships no Pi adapter to receive one. It does get a Spacedock first-officer badge and stage strips: with no `agentSetting` to read, a Pi session is taken to be a first officer when its transcript carries a `spacedock status --boot` envelope, written as a `toolResult` message. There is no Pi ensign role, and a Pi strip never bolds an entity, because Pi reports no workers to attribute one to.
- `~/.gemini/tmp/<project>/chats/session-*.jsonl` — Gemini CLI main sessions. Gemini CLI stopped serving consumer accounts in June 2026 and Antigravity CLI succeeds it there, but enterprise Code Assist and API-key use still write this store, so it is historical on a consumer machine — sessions read as idle and need `?all=1` to show — and live on an enterprise or API-key one (line 1: `sessionId`/`kind`/`directories`); `chats/<parentSessionId>/*.jsonl` are subagent recordings (linked by directory name). Flat messages and resumed-session `$set.messages` snapshots support `type: user|gemini` and per-message `tokens.output`. Legacy single-`.json` chat files are not parsed
- `~/.gemini/antigravity-cli/conversations/<session-id>.db` + `cache/last_conversations.json` + `log/cli-*.log` — Antigravity CLI (`agy`) sessions. Per-conversation DB/WAL activity provides discovery and working/idle state; trajectory-metadata protobuf fields fold fresh subagents at every nesting depth into the root card with role/type labels, and descendant activity and output usage feed the root state and token rate; stable step-metadata fields provide prompt boundaries and tool action/summary; the cache supplies the primary workspace, with CLI logs as its fallback and as the latest-prompt source. Conversation content is not decoded
- `~/.copilot/session-state/<uuid>/events.jsonl` (+ legacy `history-session-state/`) — Copilot CLI typed events: `user.message`, `session.start` (`data.context.cwd`), `tool.execution_start`, `subagent.started/completed/failed`, `session.task_complete`, `permission.requested/completed`. The permission pair joins on `data.requestId` and is what makes a Copilot row report Needs input; only the kind of prompt is read from it, never the command or the URL. A subagent's model comes off the same `subagent.started` object its name does, so the two are paired without a join, and all three subagent events are keyed on the `agentId` they share. Event `data` field names are de-facto, parsed defensively
- `~/.local/share/opencode/opencode*.db` (SQLite, read-only) — OpenCode: `session` table (`parent_id` links subagent/child sessions, `directory`, `title`, `time_updated` in epoch ms; archived sessions filtered), plus `message` joined to `part` for turns and prompts. `message` has no `type` column — the role is inside `message.data` — and the prompt text is inside `part.data`, on the parts a message typed `text`, so an attached filename never publishes as the prompt someone typed. Measured on 1.18.20: `session_message` exists, is what an earlier reading went to, and no build measured writes a row into it. The model is the `id` inside `session.model`, a JSON object OpenCode writes on the session row; the column is optional there, so a row carrying none falls back to the newest assistant message's own `modelID`, and a child session's model is read from its own row rather than inherited. Busy/idle is not persisted — inferred from `time_updated` freshness
- `~/.cursor/chats/*/<agent-id>/store.db` (SQLite, read-only) + the sibling `meta.json` — Cursor CLI: the `meta` table holds hex-encoded JSON (session name, `latestRootBlobId`, and `subagentInfo` on a child), and the sibling file holds `cwd`. Minimal support: discovery + working/idle via db/WAL mtime + title + project + the model of the newest message + subagents + a standing permission gate; no turn ETA (content is hex blobs). The gate is `pendingToolExecutionContracts` on the newest blob by `rowid` — non-empty means somebody is being asked, and `pendingToolCallStartedAtMs` beside it is when they started waiting. Newest by `rowid` and not simply anywhere, because the store is append-only and content-addressed: the blob that stood at the gate is still there long after the answer, and `rowid` is the only order the schema keeps. The key is matched on bytes, since the carrier is a length-prefixed binary frame rather than JSON, and the wait is published only while the row is fresh — an abandoned session stays pending in the file forever, so without that the board would carry a red row and a notification for a session nobody is in. A reading is also dropped when its stamp is too old to have been written by the store's own last write, since a real gate is what froze that file: that is what keeps a stamp belonging to some neighbouring record, or a message that merely quotes the field, from turning a row red with a wait nobody believes. The model is `providerOptions.cursor.modelName`, found by following the chat's root blob to the message blobs it lists and reading a bounded slice of the newest few. Cursor writes its own codename there and it is published verbatim, since mapping it to a marketing name is a guess that would silently mislabel the next codename. Blobs are plaintext on every store measured, but the store carries an encryption key it is never asked for: where the bytes do not read, the session reports no model. The workspace is `cwd` in the `meta.json` beside the store — no spelling of it appears in the `meta` payload at all — so the key spellings that payload was read for stay on as a fallback beneath it. Either source is accepted, bare path or `file://`, only when it resolves to a directory that exists, since a wrong key would label the row confidently and wrongly; when neither does, the row reads `cursor`, and a store with no `meta.json` (a subagent's has none) is a session without a workspace rather than a broken store. A subagent keeps its own store under the same workspace hash and names its agent in `subagentInfo.rootParentAgentId` — another store's directory name, which is exactly the session id another row carries — so children fold onto that row as pills labelled by `typeName` (their own name is the generic `New Agent`), each with the model read from its own store; a child whose named agent is not among the rows stays a row of its own rather than disappearing
- `~/.local/share/goose/sessions/sessions.db` (SQLite, read-only) — Goose v1.10.0+: `sessions` (`working_dir`, `updated_at` UTC, `session_type='subagent'` + `parent_session_id`; archived + infrastructure types `hidden/terminal/gateway/acp` filtered), `messages` (role, `created_timestamp`) for turns/prompts, `usage_ledger` for the token rate (`messages.tokens` is never written by goose). Per-session activity = `updated_at` column, not file mtime (shared DB) — a long single-message generation can briefly read Idle since `updated_at` only bumps on message insert. Legacy per-session `.jsonl` and the `GOOSE_PATH_ROOT` override are not supported
- `~/.factory/sessions/<slugified-cwd>/<session-id>.jsonl` — Factory Droid 0.202.0 (the older `~/.factory/projects/<project>/<session-id>.jsonl` root is still searched): line 1 `session_start` (`id`, `sessionTitle`, `cwd`); messages are Anthropic-style blocks (`role`, `content[]`, `timestamp`). The sibling `<session-id>.settings.json` is not read

Pi relocation: `PI_CODING_AGENT_SESSION_DIR` is an authoritative direct session-store override and takes precedence over `PI_CODING_AGENT_DIR`, Pi's global `sessionDir` setting, and the default. `PI_CODING_AGENT_DIR` relocates the configuration root; a relative global `sessionDir` resolves below it. A one-off Pi `--session-dir` and a project-local `.pi/settings.json` are not discoverable from this separate process. Set `PI_CODING_AGENT_SESSION_DIR` to the effective directory in either case.

## Session states

| State | Meaning | Derived from |
|---|---|---|
| **Needs input** (red, popup) | An agent is blocked on the human | Best effort, never guaranteed, and only four harnesses can report it at all. **Claude** has four sources that cover different things rather than ranking cleanly: the bundled `PermissionRequest` hook is the main one for tool gates, seen directly for `ExitPlanMode` and in the wild for `AskUserQuestion`; an actionable Notification-hook POST is the *only* source for an MCP elicitation or a worker's permission or network request; and a pending input tool seen in the transcript is an opportunistic extra, because Claude Code flushes that record on its own schedule and sometimes not until the gate has been answered; the fourth is about a subagent rather than the session, and is a member on the teams roster that was dispatched and never wrote a transcript, described on the teams-registry bullet above. **Codex** has one, its own bundled `PermissionRequest` hook, measured firing interactively with the prompt still on screen. A Codex row says a gate is open and cannot say which, because the event envelope drops the tool name at the hook; it raises a popup on the same terms a Claude one does. **Copilot** has one too, and it is the only one that needs nothing installed: the CLI writes `permission.requested` to its own `events.jsonl` when the dialog opens and `permission.completed` only once the human answers, so the collector reads a request with no answer behind it as a standing gate. A Copilot row says whether a command or a URL is being asked about, and never which command or which URL. **Cursor** takes the same route on a different store: a standing tool-call gate leaves `pendingToolExecutionContracts` non-empty on the newest blob of the chat's SQLite store, and answering it — either way — appends a blob with the map emptied. Its store closes nothing on its own, so the wait is published only while the row is fresh enough to be trusted; the reason is on the Cursor store bullet above. A Cursor row says a permission request is open and how long it has stood, and nothing about what was asked. The other six harnesses have no gate detection; Attention reports that coverage gap so a quiet row cannot be read as an all-clear |
| **Working** (blue) | Actively generating | transcript/subagent/DB activity within the last 90s; detail = in-progress task's activeForm, else running subagents, else `thinking` where the harness can see the model holding the turn with no tool call open, else last tool, else `generating…`. Pi is the one exemption from recency, in both directions — see its store bullet above |
| **Idle** (gray) | Turn ended | anything else — "awaiting your message". Two situations wear the one word: a turn that ended and nobody read the result, and a session still waiting on a reply that never came. Only a turn-end event tells them apart, so only the four harnesses with an event adapter can — Claude Code, Codex, Gemini CLI and Antigravity, and only with their hooks installed. On the other six the row says the answer cannot be known there, rather than guessing at it: it carries `Read by scanning: no turn end can be observed here`, in the session cell and again on the session page, so a quiet row is read as nothing observed recently and not as a turn that finished |

## Dashboard views

The dark-only dashboard opens on **Projects**, grouping sessions by the label their harness publishes.
**Sessions** keeps active work first and recent history below it. **Intent log** lists every
session you have typed a goal or an expected output against, including ones that have left the
board, with the revision count for each; it is the only place those words remain reachable once a
session ages off, and it holds them until the store evicts the oldest save rather than until a
date passes. Each project opens its cockpit:
a left **Scope** rail selects the project or one exact session, while a persistent briefing shows
**ASSIGNMENT / EXECUTION / COMMAND**, latest evidence, and direction. Assignment retains the
stated goal, its source, and the reason when no goal is available. Command keeps a project session
waiting on you visible above the tabs, with raise and copy-resume controls where supported.

**Now** pairs current activity with observed session endings, their outcome glyphs and git readings,
plus workflow evidence. **Course** holds observed state changes, semantic history, and completed
tasks. **Decisions** shows recorded decisions and their application state; it does not approve
them. **Console** holds Delegation, Waiting on you, Capacity, and Tripwires, followed by the
selected session's optional read-only terminal in the same panel. **Held to** appears only with a
session selected and holds the goal and expected output you typed for it, the observed entries
naming it, any direction you gave after you saved those words, the reading block, and how the
session landed as two cards that do not imply each other. Missing readings name their reason.
Browser-local
human context and tripwires do not instruct an agent, and nothing enforces the tripwires.

The state-change timeline and delegation figure use the server's local session history, survive a
restart or fresh tab, and caption the window actually observed. The cockpit's semantic history is
a separate prototype store; `--forget` does not delete it. The terminal is also a prototype: it
requires both interaction flags and registration from inside the selected session's tmux pane,
and accepts no input. Its xterm assets are vendored and served from loopback.

Exact session detail remains available from Sessions and cockpit session links, with the recorded
request, tasks, subagents, token measurements, and any answerable question attributed to it.

The route lives in the URL fragment: `#n=sessions`, `#n=projects`, `#n=attention`, `#n=intent`,
`#n=project:<encoded-project>` with the selected session and then the open tab appended when either
is set, or the full project, harness, and session identity for session
detail. Reload, pasted links, and browser back therefore preserve the selected view. Old fragments
that belonged to the retired dashboard normalize to Projects. Open the dashboard at its bare URL;
the retired `next` query is no longer a dashboard route.

The header reports event-backed running sessions and all observed subagents. When work needs intervention, a button counting
the reported blocks opens **Attention**. Keyboard shortcuts `a`, `p`, and `s` open Attention,
Projects, and Sessions unless focus is in a form control or Meta, Control, or Alt is held.
`Escape` returns from a session to its project and otherwise to Projects, under the same focus and
modifier rules. Inside a tripwire draft it cancels the draft. Breadcrumbs return through the same
project hierarchy.

MCP tools appear under the service being called rather than their wire name, for example
`Linear · list issues`. The full recorded string remains available in the row tooltip.

## Attention

Attention is a triage view. **At risk** names session evidence alongside **NEEDS YOU NOW**,
**CLOSE THE LOOP**, and **COMING NEXT**. The opening brief counts the sessions these categories
claim and describes the remainder as moving, quiet, ended, or without a counted state.
**Also at risk, off the session count** holds quota pressure, shared display labels and requests
whose session ownership is not established. Those subjects never inflate the session denominator.
**Not on this board yet** names the capabilities no source supports. Coverage details explain
missing observations instead of treating an unmeasured harness as an all-clear.

**NEEDS YOU NOW** combines native harness gates with questions registered through `ask_operator`.
Native permission prompts, plan approvals, and harness questions must still be answered in that
session's terminal; Cargento does not mark them answered on the session's behalf. A Claude Code or
Codex row therefore carries a control that copies the command that harness's own CLI takes to
re-enter that session, so reaching the terminal is a paste rather than a hunt. The other eight
harnesses publish no session id their CLI would accept, and their rows show no control rather than a
guessed command. Where Cargento can reach the terminal a session is running in, the row carries a
second control that raises it, so the hunt across tabs ends in a click rather than a paste. That
reach is narrow: macOS, tmux, a session that started while this dashboard has been up, and exactly
one terminal attached to it. Rows outside it carry no raise control at all, and the queue's coverage
details say how far the feature reached rather than repeating the absence on every row. A raise
changes what that terminal displays; it does not bring the window in front of other applications,
and nothing is ever typed into the session. The item leaves when the harness publishes evidence that the wait ended. A
question registered through `ask_operator` is different: its offered options are buttons in
Attention and in the exact session detail, and choosing one returns that option to the waiting
agent. Free-form replies are not
accepted, unanswered questions expire, and `--no-ask` disables this lane.

**At risk** names detected failed-tool loops, long-running turns, uncommitted work and conflicting
completion evidence. Waiting on the reader takes precedence over those categories; the session
still carries its observed details. Quota pressure and shared labels appear in the separate board
group. A quiet row is never promoted into proof that nothing is waiting. Only Claude, Codex, Copilot, and Cursor
currently expose a gate signal Cargento can read; the other harnesses remain explicitly unmeasured
for that question.

**CLOSE THE LOOP** identifies observed stops and session ends after waiting and risk take
precedence. The outcome vocabulary has six readings: stop or end, each with uncommitted work,
clean git state, or unmeasured git state. A stop is not a session end, and neither tells Cargento
whether you read the result, whether commits reached a remote, or why the process ended.
**COMING NEXT** groups the strongest available next action by project. Both are advisory views of
observed records, not commands sent to a harness.

## Usage and rate limits

The capacity strip sits beneath the fleet counts on Session operations. Each readable window shows
how much of its allowance is spent against how much of its own time is gone, so the two can be
compared: a window a third spent with an eighth of its time gone runs out long before one that is
nine-tenths spent with nine-tenths of its time gone. Rows are ordered by when the budget runs out at
the pace measured so far, which is not the same order as by percentage. Beneath them, what the
remaining budget buys in minutes, and how long sessions have actually worked in the project that
consumed the most measured working time, counting the intervals that opened working and were
seen to close.
Cargento never states which of the two times arrives first: the budget's end and the window's reset
sit side by side and the comparison is yours.

Quota evidence also appears in Attention, raised either by a level at or above 70 percent or by a
pace whose projected end falls before the reset. Codex reads rate-limit snapshots from its own
session files. Claude and Cursor use the harness credential only after the first-run disclosure in
the page is answered, poll their vendor endpoint at most once per five minutes while a page is open,
and never refresh, write, log, or serve the token. Until that disclosure is answered no credential
is read and no request is made, and the strip carries a switch that changes the answer later.
Cursor fetching is macOS-only, and because Cursor publishes a cycle end with no start, its row shows
a level and no clock.
Copilot contributes per-session AI Units from disk but no percentage because its entitlement is not
stored locally. Antigravity can forward quota from its status-line payload:

```json
"statusLine": {"command": "python3 <skill-dir>/notify_hook.py http://127.0.0.1:4553/api/usage", "enabled": true}
```

`--no-usage` disables credential-backed vendor fetching for a run whatever the page has stored; disk-read evidence remains.
Expired, rejected, missing, or stale quota is withheld rather than rendered as zero. Claude, Codex,
and Antigravity may publish five-hour and weekly windows, while Cursor publishes its monthly billing
cycle. Capacity bars use accent below the window's sustainable pace, amber from 1× pace, clay from 1.5×, and neutral ink when no clock supports a pace.
Model-specific Claude weekly limits remain separate because the tightest model allowance can stop
work before the account-wide window does.

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

The server writes seven files, all under `~/.cargento` (relocatable with `CARGENTO_HOME`):
`cargento-<port>.json`, which records the running instance; `cargento-<port>.log`, where a
detached server's output goes; `cargento-dismissals.json`, the sessions marked handled;
`cargento-annotations.json`, the goal and expected output you typed against a session;
`semantic-work-history.json`, the project cockpit's own record of what a project's sessions were
observed doing, bounded to a 24-hour window across at most 20 projects;
`observer/<harness>_<sid>.json`, the sidecar an observer panel records when a reader opens one; and
`cargento-history.json`, the history of what the server observed, kept for up to 14 days. A store
that cannot be read is discarded rather than repaired, the board starts empty, and the header names
which reset it was. If you
wire up Antigravity's status line, `statusline_hook.py` keeps one small memo per conversation in the
same directory so a status line that fires many times a turn posts once.

### Marking a session handled

The dismissal API remains available for integrations, but the dashboard does not currently expose
handled controls. A mark made through `POST /api/dismiss` removes that session from published
counts until anything in it writes again; a subagent write counts. Marks live in
`cargento-dismissals.json`. Delete that file to clear them all, call the endpoint with
`{"clear": false}` to restore one, or run with `--no-dismiss` to leave the store unread for a run.

### Recording what a session should achieve

You can record a goal and an expected output against one session, in your own words. Both are
optional and set independently, bounded at 240 characters each, and saving one leaves the other
alone. Select a session in the project view and open its `Held to` tab, which appears only when a
session is selected because there is nobody whose words these would be otherwise. Each field shows
how many of its 240 characters you have used as you type, offers `clear` only when there is text and `save`
only when the box differs from what is stored, and Escape puts the stored value back.

`POST /api/annotate` with a harness, a session id and either field does the same thing without the
page. It writes a numbered revision; an earlier revision is never edited, so anything citing
revision 1 still means what it meant. Send `{"clear": true}` to forget a session's words entirely,
or `settle_through` with a timestamp to mark the directions given up to that moment as settled
against the current baseline.

They are held in `cargento-annotations.json`, bounded by how many sessions carry words and how many
revisions each keeps rather than by age, because a session still on the board should not lose what
you asked of it because time passed. Delete that file to clear them all, or run with
`--no-annotations` to leave the store unread and unwritten for a run.

Binding is per session, and the board says when it is not exact. Where a harness publishes only a
short identity prefix, another session sharing that prefix would share these words, and the row says
so rather than leaving you to assume otherwise.

Below the two fields, `Held to` shows what the record lets you inspect. Work evidence lists every
observed entry naming that session with its own type and the source that published it, and states
the limit under it: demonstrated work results are read on Pi alone, so on every other harness those
entries are instructions, dispatches and gate decisions and never an inspected file, test or
deliverable. Your words also appear beside the goal the harness published, in the project view's
stated goal block, each on its own row so the two claims are never merged, and the derived row says
when the directive was observed.

A later direction gets its own block. Every instruction you gave after your newest save is listed
there with its age, and nothing there decides whether it changes what you asked for: that is yours,
and Cargento does not write into the session either way. Marking the baseline as still applying
settles them through the newest one shown, which is what `settle_through` records. The retype
control only moves the caret to the goal field, because Cargento cannot author your words. While a
later direction is unsettled a reading states no departure at all.

Reading is asked for, never running. Nothing evaluates on a cadence, so there is no drift
indicator. With nothing typed the block says there is nothing to read against; with the observer
model off it gives that reason; otherwise it states what a reading may and may not read and offers
one control. That control is disabled until an abstention check has been run and recorded, and the
evidence above stays readable while it is.

## Notifications

Three paths manage Claude's needs-input state, and a question registered through the ask lane is a
fourth alert rather than needs-input state. On macOS the server can deliver native notifications
through `osascript`, even with no dashboard tab open. Gate alerts have a 60-second per-session
cooldown and a 15-second lane-wide floor; questions have their own 15-second floor. Linux and
Windows have no native backend in this release; with a dashboard tab open, the page can deliver
browser notifications after permission is granted, for a session that starts waiting on the human
and for one that was working and has gone quiet. The dashboard shows every published item in
Attention on all platforms.

Native alerts fire on the transition into needs-input, not on every refresh. Questions notify on
arrival. Idle nudges (`idle_prompt`) can notify without marking the session blocked. The browser's
quiet nudge is close to that but not the same event: it has no hook of its own, so it fires on the
published row ceasing to look busy, and a row reaches that two ways. Where the harness's lifecycle
hooks are installed its own turn-stop reaches the row within a few seconds; everywhere else the row
turns over only once its writes have paused for as long as the working threshold. Its wording says
the session has gone quiet rather than that it is waiting on you, which is the honest reading of
either path.
Notification delivery is best effort; the dashboard's observed state remains the source to inspect.

Cargento can also check an annotated session against what you asked for without being asked, and
raise a departure while you are away. Off by default, behind `--unasked-readings`, and it is the
only thing here that spends your model capacity with nobody watching. It checks on an observed state
change rather than every turn, it raises a departure and never a reassurance, and it stops at a
per-session and a per-day limit. A spent limit is said out loud: a session nobody checked and a
session checked and found clean are different sentences on the board, because you were not there to
know which one you are looking at.

What became of an alert about a session is now recorded, one entry per raise, and that session's
panel prints it. There are five outcomes and they mean different things: handed to this machine's
notification service, the service returned an error, the command could not be started at all, the
call did not return inside its time limit, and this platform has no backend in this build. A raise
whose subject carries no session id records nothing, since the record is keyed by session. None of them is "seen". `osascript` exits zero under Do Not
Disturb and with the hosting application's notifications switched off, so a hand-over says the
service accepted the request and nothing about whether a banner was drawn or anyone was at the desk.
A raise on a platform with no backend spends no cooldown, so the next real transition is still
eligible. Beside the outcome, the panel says whether a dashboard tab has reported a notification lane
of its own and how long before the raise it did so. That is a statement about a tab, not about a
raise: a tab that opens reports and a tab that closes does not, so its absence never means the alert
missed you.

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

3. **Lifecycle events** — the plugin's own bundled hooks at `hooks/hooks.json`, so there is **nothing to add to a settings file**. They forward general lifecycle events to `/api/events/claude`: session started and ended, prompt submitted, turn stopped, permission requested, a tool run finishing, subagent started or stopped, tasks changed, compaction finished. Where path 2 sets one piece of side state, this drives the session's Working, Needs-input and Idle state directly, so the board reacts to a turn starting instead of waiting for the next scan.

   Nothing to install: enabling the plugin is enough. Note that a session's overlays are retired when it ends, which is correct and means a one-shot `claude -p` run shows no event-driven state by the time it exits. Two things survive that retirement, both held outside those overlays on purpose: the mark that its turn ended, so a run that finished and was never read can still say so, and the mark that the session itself ended, so a session that is over reads as over rather than as one sitting at its prompt waiting for you. A session with no end recorded is not known to be running — only a `SIGKILL` ends a Claude session silently, but a harness with no adapter, a session that started before the server did, and `--no-events` all look the same from here.

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

Eight events are registered: `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`, `Stop`, `PostCompact`, `SubagentStart` and `SubagentStop`. Seven have been seen firing in a real session; `PostCompact` is the exception and is mapped on Codex accepting Claude's schema rather than on a capture, which is worth knowing before trusting a compaction row. `PreToolUse` fires too and is deliberately not used, because `PostToolUse` reports the same turn once the store has actually changed.

`PermissionRequest` is the one that makes a Codex row go red, and it is worth knowing what it does and does not do. Codex blocks the tool call on the hook and applies whatever the hook returns, so this is the one event where a reporting adapter could gate the user's own work. It cannot here, and this is measured rather than reasoned: a hook on this event that printed nothing and exited 0 let the approval prompt reach the person, who approved it, and the command ran. Empty output is how Codex is told the hook has no opinion. Cargento never answers a Codex gate.

Two honest limits on that. The argument covers what the adapter *writes*, and a failure before it starts — no interpreter, an unreadable file — exits non-zero instead, which is a channel nothing here has measured. And the hook runs *before* the prompt is drawn, so its cost lands while the person is still waiting to be asked rather than after; it is one short-lived process, and the same one seven other Codex hooks already run.

### Copilot

Copilot needs nothing installed at all: its own store records the permission prompt, so the collector reads the gate straight off `events.jsonl` with no hook, no adapter and no settings file in the way. Cursor is the other harness that works this way — see below.

The CLI writes `permission.requested` when the dialog opens and `permission.completed` when the human answers, joined on a request id. A request with no answer behind it is somebody being held up, and that is what turns the row red; the answer clears it on the next refresh, whichever way it went. Measured on 1.0.78: the request was on disk in the first frame the dialog was visible in all four timed arms, and prompts stood 36, 44 and 48 seconds on a shell gate and 23 on a URL one before anyone answered.

A new prompt typed into the session also clears it, and that is the only other thing that does. The answer is never written when the terminal is closed on the dialog or the process is killed at it, so without this a resumed session carries the dead request until it ages out of the activity window — red, and ranked ahead of the work it is visibly doing. A request also has to have stood a couple of seconds before it counts, which no prompt in front of a person ever notices and which keeps a headless run's auto-denial, written and answered a millisecond apart, from being caught half-written and read as a wait.

The row says a command is being asked about, or a URL, and stops there. It never carries the command itself, the URL, or the model's stated reason for wanting either, and a typed refusal does not reach the board.

Four limits worth knowing. A session directory with no `events.jsonl` is not a Copilot row in any state, gate or no gate: 3 of the 7 directories on the machine this was measured on had none, and the collector cannot see what is not written. A headless run (`copilot -p` without `--allow-all-tools`) auto-denies every gated call in about a millisecond and raises no wait, which is correct rather than a gap, since no human was ever going to be asked. Whether an unanswered prompt eventually gives up on its own is not something this has measured; the longest observed gate ran 48.5 seconds and was answered.

The fourth is the one to know before trusting a red Copilot row overnight. A session killed at its dialog looks exactly like a person who has walked away from one — the store records the question, never the process going away, and there is no lock file or pid beside it to ask. So a row can say a prompt has been standing for hours when the terminal it was in is long gone, and the wait ends when the session drops out of the activity window rather than when the prompt does. Answering it or typing to the session is what clears it; nothing else can.

### Cursor

Cursor needs nothing installed either, and for the same reason: its own store records the prompt. While a tool call sits in front of you, the chat's `store.db` carries a non-empty `pendingToolExecutionContracts` on its newest blob, with `pendingToolCallStartedAtMs` beside it saying when the wait began. Answering — approving or refusing, it makes no difference — appends a blob with the map emptied, and the row clears on the next refresh. Measured on 2026.08.11-e8db854 across four interactive `allowlist`-mode sessions, with gates standing 15 to 244 seconds.

The row says a permission request is open and how long it has stood. It never says what was asked. The contract entry beside the map names the tool three different ways, and none of them is read.

The hook route is deliberately not taken. `beforeShellExecution` runs before Cursor decides whether to ask you, and feeds into that decision, so a hook that reported a wait from there would be reporting a prompt it had just caused — on every command, whether or not anybody was ever asked.

Two limits. The first is the one to know before trusting a red Cursor row: the store is append-only, so a session abandoned at a prompt keeps its pending contract forever, and 2 of the 10 stores on the machine this was measured on still read as waiting 29.4 hours after their process had exited. Nothing in the store records a process going away, so Cargento publishes the wait only while the session is fresh enough to be worth a row at all — the same freshness its title is gated on. That draws the line at the edge of the activity window rather than at the moment the terminal closed, which is as close as a passive reader can get.

The second is subagents. A Cursor child keeps its own store and appears as a pill on its parent's card, so a gate standing in front of a child is not read and does not turn anything red. Only a shell prompt was measured; MCP prompts, plan decisions and question tools were not, and whether they write the same record is unknown here. And where a store's blobs are encrypted — every one measured was plaintext, but the store carries a key for it — the record does not read and the session reports no wait.

### Antigravity

Antigravity has two paths, and they do different jobs.

**Hooks are bundled with the plugin** (`hooks.json` at the plugin root), so nothing needs configuring for them. They fire after a tool step and after a model invocation, and they only tell the dashboard the store probably moved, which keeps an Antigravity row fresh without waiting for the next scan. They deliberately claim nothing about whether the agent is working or idle: Antigravity's hooks can fire several times in one turn, so treating them as turn boundaries would flap the row.

**Working and Idle state comes from the status line**, which cannot be plugin-bundled, so that half is opt-in. Point it at `statusline_hook.py`, which forwards both the quota figures and the lifecycle state:

```json
"statusLine": {"command": "python3 \"<skill-dir>/statusline_hook.py\"", "enabled": true}
```

Pass a port as the first argument for a non-default instance. This replaces the older `notify_hook.py <url>/api/usage` line, which still works and still feeds the quota band; the new script additionally drives Working state and sends the quota block *alone* rather than the whole status-line document, which carries the account email and the transcript path.

Two honest limits. The conversation id is blank until a conversation exists, which is measured: the return to Idle often cannot be reported, so the Working state carries a deadline and the collector decides again after it lapses. The second one is now settled, and not the way an earlier note here guessed. The status line does report a pending tool confirmation: driven to a real permission prompt, it pushes a confirmation-pending flag beside a `tool_use` state, and in the one arm that recorded it, every flagged push carried an id that names the session. An Antigravity row still does not report Needs input, for a different reason. The status line is a repeating render rather than an event stream, so the flag arrives in a short burst as the dialog opens — two or three pushes — and then not again until something redraws the pane, and the ordinary Working and Idle pushes that follow would clear the wait rather than leave it stuck. Reporting it needs a precedence rule that does not exist yet. An agent question raises no flag at all.

Paths 2 and 3 are complementary and can both be installed. Keep `Notification` on `notify_hook.py`: Claude Code can emit an input-waiting notification for a session that then carries on running, so it stays revocable side state rather than an authoritative state change. `SessionEnd` is useful on both, which is why it appears twice above.

## Options

| Flag / URL | Effect |
|---|---|
| `--observer-model` / `--no-observer-model` | Offer optional Codex goal summaries and reader-requested readings, or refuse them for this run (refusal wins). Off by default. Each model request requires separate disclosure consent and sends at most 16,384 bytes of redacted prompt, with one call in flight per session and a 60-second timeout. Console offers the disclosure for an exact session, stores the answer in this browser, and sends content only when the reader chooses Summarize this session. A reading is the other sender: its disclosure sits above the button in `Held to`, the press itself stands in for consent rather than a stored answer, and the button stays disabled until the abstention check has been run. Quota consent authorizes neither. |
| `--interaction-origin-session <harness:sid>` / `--interaction-origin-registration-file <private-file>` | Enable the prototype terminal for one exact session only when both flags are supplied. The generated private file supplies the registration capability; registration must happen inside that session's tmux pane. Output is read-only and bounded; no terminal input is accepted. |
| `--port N` | Change port (default 4553; valid range 1–65535). If the port is busy, check `--status` first — a running dashboard may already be there; don't kill it blindly. |
| `--host A` | Bind address: `127.0.0.1` (default) or `0.0.0.0`, IPv4 only. Nothing narrower — a single-interface bind is refused rather than half-supported, because `--status`, `--stop` and the hook forwarders all reach the dashboard over loopback and such a bind does not answer there. **Nothing authenticates a remote reader**: anything that reaches the port reads every session's titles, prompts and paths, and can answer a question a session is waiting on. Prefer `ssh -L 4553:127.0.0.1:4553`; use `--host` only on a network the user would hand the transcripts to. |
| `--daemon` | Detach and keep running after the starting session exits. Prints the URL, pid and log path. |
| `--stop` | Stop the instance on `--port` over `/api/shutdown`. Returns once the port is free, so a restart on the same port works. |
| `--status` | Report whether Cargento is on `--port`: running, not running, or the port belongs to another process. Exits 0 only when running. |
| `--forget` | Delete the local history store, then exit. A one-shot command like `--stop` and `--status`, not a switch for a run: what it does is not undone by running the next command without it. Refused while a dashboard answers on `--port`, because a running instance holds its own copy in memory and would write the deleted records back. |
| `--window-hours H` | Sessions idle longer than H hours are hidden (default 24) |
| `--diagnose` | Print where each harness's data was searched for and what was found there, then exit. Use this first whenever a harness the user expects is missing — collectors skip broken or absent stores silently, so a wrong path looks exactly like an idle machine. Add `--json` for machine-readable output. Reads local paths only; it writes nothing and transmits nothing. |
| `--no-spacedock` | Do not read Spacedock workflow definitions. The role badge still shows, but the stage strips do not. |
| `--no-usage` | For this run, never fetch vendor quota over the network and ignore quota a harness pushes in, regardless of the setting stored in the dashboard. Quota a harness writes into its own store (Codex, Copilot) still shows. |
| `--no-events` | For this run, do not accept lifecycle events: no event overlays, no coarse store probe, no capability published, and the fixed-interval scan keeps the board warm instead. The rollback switch if event acquisition misbehaves. |
| `--no-git` | For this run, do not run the end-of-session git probe in any session's working repository. No git command runs at all, and every row's `dirty` and `changed` stay empty. Empty means no reading available: never attempted (including refused), attempted without a usable result, or a reading retired after resumed work. It does not mean a clean tree. |
| `--no-dismiss` | For this run, do not read or write the store of sessions marked handled: every marked session comes back onto the board. The rollback switch for the dismissal store Cargento writes on your behalf. |
| `--no-annotations` | For this run, do not read or write the goal and expected output you typed against a session: nothing is shown, nothing is saved, and the `Held to` tab offers no field and says why. The rollback switch for the one store holding prose you composed. |
| `--no-ask` | For this run, do not let a session ask the reader a question: the register, poll and answer routes refuse and the page offers no control. The rollback switch for the ask lane. |
| `--no-focus` | For this run, do not raise a session's terminal: no focus command runs, no terminal identity is recorded, and the page is handed no capability to ask with, so it offers no raise control. `--no-events` turns it off as well. The rollback switch for the terminal raise. |
| `--no-history` | For this run, keep no local history of what the server observed: nothing is written and an existing store is not read back, so the board opens with no memory of earlier sessions. |
| `--history-days N` | How long the local history keeps an observation, in days (default 14). Eviction is age first, so narrowing this drops what falls outside the window and widening it again brings nothing back. Zero or negative is refused. |
| `--history-max-bytes N` | The size cap on the local history store, in bytes (default 1048576). It is the read cap too: a file larger than it is discarded unread rather than parsed. Zero or negative is refused. |
| `http://127.0.0.1:4553/?all=1` | Show all sessions ever, including idle ones |
| `/api/data` | Raw JSON, same data as the UI |
| `/api/health` | Liveness and identity (pid, port, start time). Scans nothing, unlike `/api/data`. |
| `/api/overlays` | Diagnostic: the live event overlays behind each session's state, with their arrival order and timings, plus a record of every time an event overruled a session the dashboard had read as waiting. Use this when a row's state disagrees with what the agent is actually doing and you need to know whether an event said so or never arrived. Empty is a real answer. Absent under `--no-events`. |
| `/api/stream` | Server-sent events, one per new revision. This is what keeps an open page current, so it refetches when something changed rather than on a timer; one tab per browser holds the connection. A browser without `EventSource` falls back to polling. |
| `POST /api/shutdown` | Stop the server. Loopback-only, with the same origin checks as `/api/notify`. |
| `POST /api/usage` | Receive a harness's own quota, forwarded by its status-line command (see Usage and rate limits). Loopback-only, same origin checks. Stores in memory only. |
| `POST /api/dismiss` | Mark one session handled, or with `{"clear": false}` put one back. Body is `{"harness", "sid"}` and carries no timestamp — the watermark is the server's clock. Answers `persisted: false` when the store could not be written. 503 under `--no-dismiss`. |
| `/api/cleared` | The sessions marked handled: a harness key, a session id and when each was marked, and nothing else. 503 under `--no-dismiss`. |
| `/api/annotations` | Every session you have typed a goal or an expected output against, including sessions no longer on the board. Serves the words themselves, so it is read when the Intent log is opened rather than on the refresh loop. 503 under `--no-annotations`. |
| `POST /api/reading` | Ask for one reading of a session against the words typed against it, the same press the `Held to` button makes. Body is `{"harness", "sid", "press": true, "observer_model": 1}`, capped at 4096 bytes, loopback-only and refused on a document navigation. 503 under `--no-annotations`, with the observer model off, or while the abstention check has not been run, which is every build so far. 409 while a reading for that session is already in flight, and 200 with `produced: false` when there is no annotated session by that name. |

## Interpretation notes (share with the user if asked)

- **A quiet session is not proof nothing is waiting.** Only Claude, Codex, Copilot, and Cursor can
  report a gate. Attention names missing coverage and collector errors rather than turning them into
  zero. A question registered through `ask_operator` is separate and can belong to any harness.
- **Age** on a task is creation to now, or creation to last update when complete. Claude task files
  expose timestamps; Codex plan steps do not, so Codex task rows show no borrowed age.
- **Output rate** is output tokens over the last ten minutes, not billed input or cache tokens.
  Claude, Codex, Pi, Gemini CLI, Antigravity, and Goose expose usable generation totals. Missing
  harnesses make aggregates a floor, never a measured zero.
- **Model and consumption** come only from records a harness writes. Claude, Codex, Pi,
  Antigravity, Copilot, and Cursor can report a model. Copilot alone provides per-session AI Units;
  those units are not converted to dollars or summed across harnesses.
- **Current-turn estimates** compare elapsed generation time with completed turns from the same
  session. They are withheld when there is no defensible sample. A quiet gap longer than five
  minutes re-anchors elapsed time so a permission wait is not counted as generation.
- **Loop detection** reads one request three ways, and the note says which one fired. Four
  consecutive failed Claude tool calls is the tight run. Six failed calls in the request however
  they were spaced, and more failures than successes, is the total, which no success resets, and it
  catches the request that fails three times, succeeds once, then fails three more, where the run
  alone reads as clean. Three failed calls with none succeeding at all is a request where nothing
  has worked yet. The count alone is not enough for the second of those: six scattered failures
  among two hundred successful calls is ordinary work, so the failures have to outnumber the
  successes as well. The last two readings are withheld entirely when the scan started partway
  through a request, since both describe the whole of it. Other harnesses do not expose a verified
  failure field, so Cargento does not infer any of the three there. The pattern is evidence, not proof; iterating on a failing test can look
  the same from outside.
- **Project** is the last two path segments when the working directory is known. This keeps sibling
  repositories distinguishable without printing an entire path. The fallback harness label is not
  treated as proof that two sessions share a directory.
- **Session identity** includes harness, project, and the complete session id. Displayed ids widen
  beyond eight characters when nearby rows would otherwise collide. Detail routes carry the full
  identity so similarly prefixed sessions cannot alias.
- **The line beneath a session title** is the strongest current instruction Cargento can attribute:
  newest operator request, current agent statement, or an earlier substantive request when the
  newest prompt is only a continuation such as `proceed`. It carries its source and age and is
  absent when attribution would be a guess.
- **`…REDACTED`** means a credential-shaped value was replaced before it reached the page. The
  original still exists in the harness transcript on disk, so rotate a real credential rather than
  treating the marker as remediation.
- **Spacedock evidence** is bounded and freshness-gated. Stage, entity, and delegation readings are
  omitted when the workflow definition or measured window cannot support them. A missing strip is
  not a claim that no workflow exists.
- **"Source not fully read"** on a row means Cargento opened that session's store and could not read
  every part of it, and it names which readings are missing. What the row still shows was read
  normally; the named readings are absent rather than zero, which matters most for a token rate,
  where nothing else separates a missing measurement from a measured zero. The five harnesses whose
  store is a database can report it: Antigravity, Copilot, Cursor, Goose, and OpenCode. A row
  without the line is not a promise that everything read, only that nothing reported otherwise.

## Stop

```bash
python3 "<skill-dir>/server.py" --port 4553 --stop
```

The command uses `POST /api/shutdown` and waits for the port to come free before reporting success,
so you can start a fresh instance on the same port straight afterwards. It also clears a state file
left behind by a server that was killed,
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

- Do not widen the bind in code. The default is `127.0.0.1` and `--host 0.0.0.0` is the operator's own opt-in (see the flag table above), never something to set for them: anything that reaches the port reads every session's titles, prompts and paths.
- A harness the user expects is missing: run `--diagnose` before guessing. It distinguishes "no store here", "store present but unreadable", and "store read, no recent sessions" — the collectors cannot, because they skip unreadable stores silently by design.
- Headless Linux (no graphical session): `python3 -m webbrowser` and `notify-send` both need a desktop. Reach the dashboard over SSH with `ssh -L 4553:127.0.0.1:4553 <host>` and open it locally. If running it under systemd, use a **user** unit — a system unit expands `~` to `/root` and `ProtectHome` hides every harness store.
- Flatpak- or Snap-installed harnesses write inside their sandbox, and Snap's `home` interface excludes dotfiles like `.claude`. Cargento running outside the sandbox will not see them; `--diagnose` shows where it looked.
- Very long Windows paths: Claude's encoded project directory names are long by construction, and without `LongPathsEnabled` a store can exceed the 260-character limit. Those transcripts are skipped rather than crashing, so the symptom is missing sessions — `--diagnose` reports the root it scanned.
- On Windows, Cargento briefly holds a transcript open while reading it, and Python cannot request `FILE_SHARE_DELETE`. If a harness rotates that exact file in that window it may see a sharing violation. Reads are short and bounded, but the window is not zero; there is no way to close it from Python without native calls.
- A session stuck on "Needs input" after you already answered: the state clears on the session's own next transcript write — its own, not a subagent's, since a background agent writing says nothing about whether you have answered. `SessionEnd` clears it on a clean Claude exit, and a server restart also clears hook-reported notifications (they're in-memory). An abrupt kill cannot be distinguished from a terminal left open at a prompt, so it clears only by a later transcript event or restart.
- After two missed refreshes, the live header changes to "stalled" and shows the last successful update — restart the server, no need to reload the page.
