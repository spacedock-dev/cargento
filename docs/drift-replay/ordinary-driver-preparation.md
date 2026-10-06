# Ordinary persisted-turn preparation

`scripts/ordinary_turn_driver.py` prepares the four engineering walks on one final
revision: default with a fresh Allow, monitor with ten ordinary persisted turns,
no installed harness, and declined consent. It does not run Analyze or invoke a
provider from its command line. The ordinary cap is ten attempts, separate from
review launches and Analyze calls. Allowances cannot transfer. Preparation does
not activate any existing budget.

```bash
python3 scripts/ordinary_turn_driver.py --revision <full-final-revision> \
  --manifest-out <new-private-manifest-path>
```

The destination must not exist. The output has mode 0600 and four blocked run
records. It binds the proposed revision, expected consent and model-call
behavior, and the artifacts still needed. Preparation is not capture readiness.
The root operator fills the private bindings and reviews unreachable surfaces;
the helper does not invent a session, a network export, or a Copy readback.

## Execution admission

The Python execution entry point is `run_turn(plan, adapter)`. Its default adapter
and authority binding are absent. An external trusted Python controller must bind
`AUTHORITY_DIR` to the existing original budget directory and `GRANT_SHA256` to
the independently reviewed existing grant identity. The helper discovers neither
from a checkout, `HOME` nor `CARGENTO_HOME`. This binding is a trusted controller
capability; the helper cannot prove the controller chose the original authority.
A missing, disabled or malformed budget refuses. A changed grant refuses. There
is no CLI or environment option to select, activate, initialize, reset or migrate
an authority. An open charge or held result requires explicit cleanup and review;
process liveness never automatically clears it.

`NativeAdapter` composes two externally reviewed implementations:

- `NativeConfiguration.admit` must establish effective native flags, actual
  model and effort, final checkout revision, owned workspace, persistence,
  tools, installed plugins, managed/global/project settings, hooks, MCP and the
  exact environment. Unknown customizations refuse. An explicit settings file
  and `--setting-sources` are not a claim that installed or managed
  customizations are isolated. `capture` reads the admitted persisted transcript
  and the owned native hook capture; it does not write into a session.
- `CompleteObserver.admit_controller` must admit only the current controller's
  owned ancestry before any future child starts. The resulting scope confirms
  admission and current loss state immediately before the native child, records
  attributable events, and stops/reconciles every owned descendant at cleanup.
  It must handle escaped groups, PID reuse and inherited connections. No
  implementation of this facility is supplied here.

Complete-observer acceptance remains an external **required** gate. Independent
ground truth must reconcile twenty short flows, twenty short execs, long-lived
controls, immediate children and grandchildren, group escapes, PID churn/reuse,
inherited connections, IPv4/IPv6 and UDP, failure/cancellation and injected loss.
Admission must precede capture, and start/end readiness and loss must be
measured. Any unaccounted path, dropped event or unknown inherited connection
blocks acceptance. Neither a protocol hash, a JSON `passed` value nor these stub
tests can certify the facility. The existing failed short-flow/exec evidence
remains failed.

## What the prepared controller enforces

Each attempt binds a full native UUID, exact prompt digest, model, effort,
workspace, revision, argv, environment, CLI/settings/hooks/MCP file identities,
owned board port, owned `CARGENTO_HOME` and native transcript path. File hashes
are rechecked around admission. The owned home must differ from the account's
default Cargento home, and the three owner's board ports are refused. The
configuration admission must verify the actual opened runtime/configuration
and custom hooks use the owned board port; hashes alone do not prove this.

The durable charge is written under a cross-process lock before launch. A
second durable latch permits one native child start per charge, including across
new process-guard instances. Attempt ordinals are serial, at most ten; no retry,
refund or fallback is automatic. The same session and campaign bindings persist
across turns; only initial creation versus resume and the expected prompt change.

A completion-write error attempts a held transition without refunding the charge
and still raises the original error. A persistent filesystem failure can defeat
that hold. In particular, a failed directory fsync after replacement can leave a
visible completed, nonrefunded record whose durability is uncertain. The external
controller must stop and inspect the original budget before another attempt;
neither the exception nor a visible completion proves a durable hold or completion.

The concrete POSIX subprocess guard passes the exact argv, workspace,
environment and prompt without a shell. It bounds wall time at 900 seconds and
aggregate captured stdout plus stderr at 4 MiB. It drains both streams, closes
stdin, refuses nonzero exit, and cleans up its owned group on interruption or a
limit. Group cleanup is corroboration only: reaped numeric group IDs are not
signaled again, and the external observer must prove exact remaining-descendant
cleanup. Windows native execution refuses; no Windows readiness is claimed.

`claude_arguments` prepares help-listed persistence/hook flags. It passes the supplied
full UUID to `--session-id` for the first turn and to `--resume` subsequently, preserves hooks and session
persistence, and omits `--no-session-persistence`, `--safe-mode` and `--bare`.
These flags are preparation, not proof that the installed CLI persists or emits
the required native events. The exact command still needs native configuration
admission; AGY native execution has no prepared configuration admission here.

CLI exit does not complete a turn. The capture must extend the prior exact source
prefix, add one exact person prompt, join its native parent UUID DAG and end at
the newest explicit `end_turn`. Scoped native `UserPromptSubmit` and `Stop` payloads
must join the same full UUID, prompt, workspace and transcript. New parent records
need nonempty UUIDs unused in the prior prefix, matching roles and parent-session
identity, and no meta or child markers. Added messages before the new person
anchor refuse. Sibling branches rooted in that person remain valid; strict linear
adjacency is not required. Source and hook bytes must remain stable through cleanup
and observer close. The external scope
must independently bind those hook records to this capture interval. Failed joins,
loss, incomplete cleanup, violated limits or any Cargento model call attempt to hold
the charge. Ordinary agent-provider traffic is separately attributable; the monitor,
declined and no-harness walks require zero Cargento model calls.

## Verification limits

Focused tests use temporary private authority files, injected synthetic scopes
and local Python fixture CLIs. Their completed status is `synthetic-joined` with
`real_turn_proof: false`. They verify accounting, refusal paths, subprocess bounds
and source joins. They do not prove native persistence, observer completeness,
live hook behavior, real session fidelity or any of the four walks.

The adapter is a trusted reviewed Python boundary, not a plugin loaded from a
JSON report. A local owner can rewrite code, grants, budgets, adapters and
receipts. That accepted exposure is not cryptographic authority. The operator
must review independent observer and native evidence before activating the
existing budget or registering a real adapter. The privacy rulings remain in
[SECURITY.md](../../SECURITY.md) and the [reading design](../design-reading-a-session.md).
