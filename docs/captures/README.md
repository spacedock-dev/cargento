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
| `gemini/hooks-0.53.1-macos.jsonl` | Four headless `gemini -p` turns, 56 hook invocations, each turn containing one `list_directory` tool call. Gemini CLI 0.53.1, macOS, against an isolated `GEMINI_CLI_HOME`. No credential was involved: the CLI ran against a loopback stand-in for the Gemini API, which is what made a real session reachable at all, since consumer accounts have not been served since 2026-06-18 and the auth check happens before any hook fires. |
| `gemini/identity-0.53.1-macos.jsonl` | The identity question for the same five sessions, as verdicts rather than values, in the shape the Antigravity file established. |

Not every capture is a payload record. `codex/permission-hook-0.146.0-macos.jsonl` answers a question no payload could, because the payload never arrives: it pairs what each run asked for with the policy it was actually given, which is what turns "the hook did not fire" into "the hook cannot fire, and here is the mechanism".

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
