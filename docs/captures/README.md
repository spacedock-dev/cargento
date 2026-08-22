# Captured hook evidence

Recorded payload **shapes** from real harness sessions, kept as the evidence behind the adapter
semantics gate in
[`../plans/event-driven-session-observation.md`](../plans/event-driven-session-observation.md).
A gate that says "measured" should be able to show its measurement.

Most files here are hook payloads. One is not: `claude/usage-endpoint-macos.jsonl` records the shape
of a vendor HTTP response, and the claims it backs live in
[`../design-usage-quota.md`](../design-usage-quota.md). It is kept here because it obeys the rule
this directory exists for — shapes, never values.

## What is in a record, and what is deliberately not

Each line is one hook invocation, written by `scripts/capture_hook.py`. It records the **names** of
the payload's fields and nothing about their values:

- `event` is the native hook name, and `keys` is the sorted field list, which is what an adapter is
  actually written against;
- `session` is the first eight characters of the session id, and `project` is a salted hash of the
  working directory, so records can be grouped into turns without naming anything;
- `tool` is the tool name, `hook_ms` is the hook's own cost, `os` and `at` place the run;
- `harness` names which harness produced the line, from format version 2 onward. Version 1 lines
  carry no `harness` and are read as Claude, which is what they all were.

A harness is recorded rather than inferred from the filename because the reporter bounds a turn with
each harness's own pair of event names, and getting that wrong is not a cosmetic error: the first
Gemini capture reported "no complete turn" across four complete turns, because it was being measured
against Claude's `UserPromptSubmit` and `Stop`.

No prompt text, no tool input, no tool output, no file path. `PreToolUse` records that a
`tool_input` field existed; it does not record what was in it.

## Files

| File | Provenance |
|---|---|
| `codex/hooks-0.146.0-macos.jsonl` | One `codex exec` turn containing one shell tool call. codex-cli 0.146.0, macOS, run against an isolated `CODEX_HOME` so no user configuration was touched, with `--dangerously-bypass-hook-trust` because Codex skips untrusted hooks silently. |
| `codex/subagents-0.146.0-macos.jsonl` | One `codex exec` turn that spawned one sub-agent via `spawn_agent`/`wait_agent`, 10 hook invocations. codex-cli 0.146.0, macOS, isolated `CODEX_HOME` with the plugin installed through a scratch marketplace, and `--dangerously-bypass-hook-trust` because Codex skips untrusted hooks silently. Settles whether a subagent hook's `session_id` is the parent's. |
| `codex/identity-subagents-0.146.0-macos.jsonl` | The parentage verdicts for that turn: whether `session_id` matched the parent turn, and whether `agent_id` is the child's own thread id. |
| `codex/permission-hook-0.146.0-macos.jsonl` | Two `codex exec` runs asking for a write under a read-only sandbox, with `PermissionRequest` registered alongside seven proven names. codex-cli 0.146.0, macOS, isolated `CODEX_HOME`. A **negative** capture: it records what each run requested, what policy it actually ran under, and which hooks fired, so the reason the event never arrives is evidenced rather than asserted. |
| `antigravity/statusline-macos.jsonl` | Two `agy --print` sessions, 37 status-line pushes. macOS. Recorded through a `statusLine` entry in the real `settings.json`, backed up and restored in the same script, because Antigravity's status line cannot be plugin-bundled. |
| `claude/hooks-2.1.222-macos.jsonl` | Five headless `claude -p` turns, 38 hook invocations: one turn with three tool calls, one that dispatches a subagent which itself calls a tool, and three that pursued a permission prompt. Claude Code 2.1.222, macOS. Recorded through `--plugin-dir` against a copy of the plugin whose hook commands were repointed at the recorder, so no settings file was edited. **Not** through an isolated `CLAUDE_CONFIG_DIR`: that changes the credential's keychain account name and loses the subscription login. |
| `claude/identity-2.1.222-macos.jsonl` | The identity question for the same five sessions, as verdicts, covering both `session_id` and the subagent `agent_id`. |
| `claude/usage-endpoint-macos.jsonl` | Two live `GET /api/oauth/usage` responses a day apart, on a subscription account with extra-usage credits disabled. macOS, 2026-08-06 and 2026-08-07. The second reading exists to test which fields hold still, and it earned its place: `is_active` moves between the two, and the record computes that by comparing the readings rather than asserting it, which is why nothing renders that field. Written by a one-off purpose-built recorder rather than `capture_hook.py`, on the precedent the Antigravity file set: there is no hook anywhere in this path, only a response, and the token came from the same Keychain item `quota.py` already reads. Settles what `limits[]` actually contains, whether `utilization` is a percent or a fraction, and which of the per-model field names are alive on a subscription plan. |
| `claude/permission-decision-2.1.238-macos.jsonl` | Ten interactive Claude sessions driven to a real permission prompt through `tmux`, with a `PermissionRequest` hook that returns a candidate decision. Claude Code 2.1.238, macOS. A **negative** capture in the shape `codex/permission-hook` set: six decision spellings each got their own fresh session, and each was ignored. The seventh run is the control that makes the verdict safe — an *invalid* value for a recognised field should produce a validation error naming it, and none was reported, so the field is unread rather than rejected. Two further runs answer the timing half: the gate reaches the human 0.9s after the hook is entered whether the hook sleeps 30s or 60s, so the hook is not awaited and a slow hook cannot delay the prompt. Sessions were driven one arm apiece because reusing one made the model read a cancelled gate as a denial and refuse to retry. Settles DRC-4163, and therefore DEC-2 option B on Claude. |
| `gemini/hooks-0.53.1-macos.jsonl` | Four headless `gemini -p` turns, 56 hook invocations, each turn containing one `list_directory` tool call. Gemini CLI 0.53.1, macOS, against an isolated `GEMINI_CLI_HOME`. No credential was involved: the CLI ran against a loopback stand-in for the Gemini API, which is what made a real session reachable at all, since consumer accounts have not been served since 2026-06-18 and the auth check happens before any hook fires. |
| `gemini/identity-0.53.1-macos.jsonl` | The identity question for the same five sessions, as verdicts rather than values, in the shape the Antigravity file established. |
| `claude/mcp-ask-gate-2.1.239-macos.jsonl` | Three `ask_operator` calls in one attended session, at default permission settings, in a directory that had never seen the tool. Claude Code 2.1.239, macOS. Registered with `--mcp-config --strict-mcp-config`, driven through `tmux`. There is no hook in this path, so a purpose-built recorder wrote it, as `claude/usage-endpoint-macos.jsonl` did. It exists because the measurement DEC-2 rests on was taken headless with permissions pre-granted, and re-running it attended changes the answer: the first call raises a terminal gate **before** `tools/call` reaches the server, so the dashboard has nothing to show until the human has already walked to the terminal. The third call, taken after the persistent grant, is the other half of the verdict — the gate is once per directory, not once per call. Also records that a stdio server inherits `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PROJECT_DIR`, which is where a question card's attribution comes from. |
| `codex/mcp-ask-gate-0.146.1-macos.jsonl` | The same arrangement on codex-cli 0.146.1, macOS, at default approval policy: one call, gated, then held and delivered. The second harness for the file above, and it replicates the finding with a three-tier grant rather than two. Run against an isolated `CODEX_HOME` whose `auth.json` was symlinked rather than copied, because an isolated home carries no credential and no sign-in was driven; the grant landed in the isolated home, so no user configuration was written. |

Not every capture is a payload record. `codex/permission-hook-0.146.0-macos.jsonl` answers a question no payload could, because the payload never arrives: it pairs what each run asked for with the policy it was actually given, which is what turns "the hook did not fire" into "the hook cannot fire, and here is the mechanism".

`claude/permission-decision-2.1.238-macos.jsonl` is the same kind of file for the opposite problem: the hook fires every time, so what needed evidencing was that its *return value* is discarded. A run that returns the wrong spelling and a run against a harness that reads no spelling at all look identical, which is why the invalid-value control is in there. Its timing half also corrects a measurement error worth recording: a first attempt timed the gate from the hook's exit log, which is written after the hook sleeps, and so reported a 91s wait that was the instrument rather than the harness.

The two `mcp-ask-gate` files record a third kind of thing: not what a payload contains, but what the
harness does in the silence before one arrives. Their load-bearing field is a negative —
`tools_call_seen_by_server_before_gate` — because the whole finding is that the server sees nothing
while a human is being asked. They also carry the arrangement in more detail than the other files do,
which is deliberate: the run they correct was invalid on its arrangement rather than its readings, and
a child session silently inheriting its parent's permission mode is the kind of confound that reads as
a result.

The two identity files exist because a shape-only record cannot answer the question the gate asks.
`capture_hook.py` truncates a session id to eight characters on purpose, and the question in both cases
was whether the hook's *whole* id is the value the collector keys on.

For Gemini it is the `sessionId` on line 1 of the `chats/session-*.jsonl` the same session wrote. Five
sessions, five exact matches, all 36 characters. The store *filename* carries only the first eight,
which is the trap: keying on the name would key on a prefix the collector never uses.

For Claude the file answers two questions rather than one. `session_id` is the whole 36-character UUID
and the transcript filename stem *is* that value, five times out of five, so the collector taking
`basename(fp)[:8]` and the adapter taking `session_id[:8]` agree by construction rather than by luck.
The subagent `agent_id` is a separate 17-character value that is **not** UUID-shaped, which is worth
recording as a constraint: anything that validated `subagent_id` the way `session_id` is validated
would drop every Claude subagent overlay.

The Antigravity file has a different shape from the Codex one, because it answers a different
question. Its records carry `keys`, the observed `agent_state`, and `id_verdicts`: for each candidate
id field, its length, whether it named a real `conversations/<id>.db`, and whether it equalled
`session_id`. **Verdicts rather than values** is the point: the question was whether the ids match
what the collector keys on, and that can be answered without recording an id at all.

The usage-endpoint record is the extreme case of that, because a quota response is *all* values:
one account's percentages, its reset stamps, its balance. So every number in it becomes a scale
verdict — `float 0..100 (percent scale)` for `five_hour.utilization`, `int 0..100` for a
`limits[]` element's `percent` — which is the only thing a parser needs from them and is not a
figure about anyone's usage. `scope.model.display_name` is recorded as presence alone for the same
reason: whether the field arrives decides whether a per-model row can be labelled, while its value
is a model name attached to one person's plan. Null-valued keys are written down as `null` rather
than dropped, so a field name that exists and is dead on a plan stays distinguishable from one that
was never sent — which is the whole finding about `seven_day_opus`.

## Two shapes measured with no file to capture

Publishing the model each session runs on reads two store records that no hook carries, so
`capture_hook.py` had nothing to intercept and no file was written for either. The field names are
recorded here anyway, because the parsers are written against names and a name is the whole
contract. Names and counts only, as everywhere else in this directory: no payload values, no blob
bytes, and never a `blobEncryptionKey`, which is a credential whatever the store it sits in.

Codex writes a `turn_context` record at the head of every turn, one to six lines after each
`task_started`. Across 364 rollout files on codex-cli 0.146.0, macOS, its `payload` carried these
keys and no others: `approval_policy`, `collaboration_mode`, `comp_hash`, `current_date`, `cwd`,
`effort`, `file_system_sandbox_policy`, `model`, `multi_agent_version`, `permission_profile`,
`personality`, `realtime_active`, `sandbox_policy`, `summary`, `timezone`, `turn_id`,
`workspace_roots`. `model` is the only one read. There is no provider key, which is why a Codex row
leaves `provider` unset rather than deriving one from the model name.

Two timings settle where that record has to be read from, and they are the reason it is not read
where every other Codex display field is. The last `turn_context` in a rollout sits beyond the
400 KB transcript tail in 117 of 312 files that have one, which is 37.5%, at a distance from the end
of file with a median of 273 KB and a maximum of 3.0 MB. It sits inside the 8 MB turn-scan budget in
312 of 312. A parser written against the tail passes every small fixture and reports no model for a
third of real sessions.

Copilot's `subagent.started` event carries the child's label and the child's model on one object,
which is why the two need no join. Inside `data`: `model`, and the label under `name` with
`agentName`, `agent` and `agentType` as the fallback spellings the reader tries in that order. At
the top level of the event: `agentId`, which holds the same value on `subagent.started`,
`subagent.completed` and `subagent.failed`, and is also the value the billing ledger's `agent_id`
column holds. The top-level `id` does not: `completed` carries a different one from `started`, so a
reader keyed on `id` never matches and falls through to a drop-oldest fallback, which is right for
one child and wrong for two.

## Reading one

One directory per harness, because the reporter summarises a whole directory and two harnesses with
different record schemas in one directory produce a report that reads as a single confused harness:

```bash
CARGENTO_CAPTURE_DIR=docs/captures/codex python3 scripts/capture_hook.py --report
```

That prints cardinality, per-event field shape, turn orderings and the hook-cost distribution: the
four things the gate asks for.

The Antigravity records were written by a purpose-built recorder rather than by `capture_hook.py`,
because the question there was whether an id *value* matched a conversation database and a
shape-only recorder cannot answer that. Read them directly:

```bash
python3 -c "import json,sys; [print(json.loads(l)['agent_state'], json.loads(l)['id_verdicts']['conversation_id']) for l in open('docs/captures/antigravity/statusline-macos.jsonl')]"
```

`claude/usage-endpoint-macos.jsonl` came from a purpose-built recorder for the other reason: there
is no hook in that path to intercept, and one request answers the question. It is a single line, so
read it whole:

```bash
python3 -c "import json;[print(json.dumps(json.loads(l),indent=2)) for l in open('docs/captures/claude/usage-endpoint-macos.jsonl')]"
```
