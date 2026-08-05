# Captured hook evidence

Recorded payload **shapes** from real harness sessions, kept as the evidence behind the adapter
semantics gate in
[`../plans/event-driven-session-observation.md`](../plans/event-driven-session-observation.md).
A gate that says "measured" should be able to show its measurement.

## What is in a record, and what is deliberately not

Each line is one hook invocation, written by `scripts/capture_hook.py`. It records the **names** of
the payload's fields and nothing about their values:

- `event` is the native hook name, and `keys` is the sorted field list, which is what an adapter is
  actually written against;
- `session` is the first eight characters of the session id, and `project` is a salted hash of the
  working directory, so records can be grouped into turns without naming anything;
- `tool` is the tool name, `hook_ms` is the hook's own cost, `os` and `at` place the run.

No prompt text, no tool input, no tool output, no file path. `PreToolUse` records that a
`tool_input` field existed; it does not record what was in it.

## Files

| File | Provenance |
|---|---|
| `codex-hooks-0.146.0-macos.jsonl` | One `codex exec` turn containing one shell tool call. codex-cli 0.146.0, macOS, run against an isolated `CODEX_HOME` so no user configuration was touched, with `--dangerously-bypass-hook-trust` because Codex skips untrusted hooks silently. |

## Reading one

```bash
CARGENTO_CAPTURE_DIR=docs/captures python3 scripts/capture_hook.py --report
```

That prints cardinality, per-event field shape, turn orderings and the hook-cost distribution: the
four things the gate asks for.
