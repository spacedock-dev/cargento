---
commissioned-by: spacedock@0.26.0
entity-type: task
entity-label: task
entity-label-plural: tasks
id-style: sd-b32
state: .spacedock-state
trunk: main
stages:
  defaults:
    worktree: false
    concurrency: 2
  states:
    - name: backlog
      initial: true
      gate: true
    - name: ideation
      gate: true
    - name: implementation
      worktree: true
    - name: validation
      worktree: true
      fresh: true
      feedback-to: implementation
      gate: true
    - name: done
      terminal: true
---

<!--
  Adapted from iamcxa/qnow docs/dev/README.md at
  d15eccb935e3255e5c5a48fc511ce029b8def0e1.
  The workflow specification, mods, and measurement ledger are shared in the
  Cargento repository. Runtime concerns belong to the Spacedock binary; this
  README owns workflow judgment and evidence discipline.
-->


# Cargento — Development Workflow

Cargento is a markdown-first, cross-harness agent cartography plugin. This
workflow ships changes to its shared skill, stdlib-only Python dashboard,
manifests, validators, release automation, and owned documentation without
breaking Codex, Claude Code, Antigravity/AGY, Gemini CLI, or supported host
platforms. The repository contract and canonical pre-PR suite live in
`AGENTS.md`.

Tasks move `backlog → ideation → implementation → validation → done`. One
gated design stage (ideation), one worktree build stage (implementation), one
fresh-context verification stage (validation) with `feedback-to`
implementation, and a terminal merge. The spacedock binary owns all runtime
semantics: stage transitions, gate records, worktree lifecycle, state
durability, exactly-once approval. This README owns judgment discipline only.

## File Naming

Each task is `{slug}.md` (default) or a folder `{slug}/index.md` when
per-stage artifacts accumulate. Slugs: lowercase, hyphens, no spaces. Task
state lives in the split-root state checkout (`state:` above) so stage
transitions never churn the code branch.

The workflow specification, `_mods/`, and `ledger.csv` are git-tracked and
shared. Only `docs/dev/.spacedock-state/` stays local: it is an independent Git
repository on the `spacedock-state/dev` branch, ignored by the product
repository, and deliberately has no `origin`. Spacedock therefore commits
state changes path-scoped inside that repository and attempts no pull or push.
Each workspace has its own state checkout and exactly one session owns its
mutations. Verify the workspace's state owner before filing:

```bash
git -C docs/dev/.spacedock-state rev-parse --abbrev-ref HEAD   # expect spacedock-state/dev
```

Never publish or copy the split-root state checkout into the product
repository. The tracked workflow files describe the shared process; they do
not make entity receipts portable or create an automatic state-publishing
path.

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | SD-B32 stored ID from `status --next-id --id-seed <slug>` |
| `title` | string | Human-readable task name |
| `status` | enum | backlog, ideation, implementation, validation, done |
| `source` | string | Where the task came from (captain note, issue, defect, audit) |
| `started` / `completed` | ISO 8601 | `started` at the first transition out of `backlog`, `completed` at the `done` transition — `wallclock_hours` is their difference, so a task that sits in the queue for a week does not bill that week |
| `verdict` | enum | PASSED or REJECTED — set at final stage |
| `score` | number | Optional priority score from 0.0 to 1.0 |
| `worktree` | string | Set on first worktree dispatch, cleared at terminal merge |
| `issue` / `pr` | string | External references |
| `design` | enum | `required` or `trivial-pass` — set at ideation, or at filing for a `lane: defect` task, which has no ideation stage. May be empty only while the task is still in `backlog`; never empty once it leaves |
| `lane` | enum | `defect` or `main` — the FO's Defect-lane classification, recorded at filing so it is queryable (`status --where lane=defect`) instead of re-derived by re-reading every body. `defect` asserts all four conditions below hold |

## Proof Policy

Inherited from the spacedock proof discipline; the six rules below are
binding in every stage report and every gate review.

1. **No prose-grep, and provenance decides independence.** A string match
   over an instruction file the model reads never proves a behavioral claim.
   A grep may serve as one-off evidence for an existence fact in a validation
   report; the same grep committed as a test is banned — it cannot fail. And
   a check the author wrote to grade the author's own artifact is a self-issued
   stamp, not a gate. This is about what closes a gate, not about who may write
   a test: the worker's own RED-before-GREEN tests are exactly the evidence
   this workflow asks for, and they become insufficient only when they are also
   offered as the independent verdict on themselves. Independence at a gate
   comes from the fresh-context validator and the cross-model pass, never from
   the artifact grading itself.
2. **Evidence must be able to fail.** Each AC's cited evidence names the
   concrete change that would flip it. If the author cannot name the
   falsifying edit, the criterion does not count.
3. **Prove behavior by exercising it.** Output bytes, exit codes, resulting
   on-disk state, a browser actually driving the flow. Unit tests prove logic;
   they do not prove wiring. Seam-level claims need runtime or E2E evidence.
4. **Trace every mechanism to value.** Any new mechanism names the value AC it
   serves, the simplest alternative considered, and why that alternative is
   insufficient. A test harness orchestrates and observes the supported
   runtime; it never becomes a second implementation of the system under test.
5. **Automatic must-pass behavior checks live at stage boundaries, never in
   the worker's inner loop.** Hooks that fire on every commit/edit inside a
   work session are limited to fast mechanical checks (format, lint,
   typecheck). Behavioral or corpus/consistency checks, *as must-pass gates*,
   belong to the validation gate and CI: a must-pass check inside the inner
   loop turns "implement the behavior" into "make the check shut up", and the
   worker will drift the implementation — or the check's inputs — to satisfy
   it. This governs checks the tooling forces, never tests the worker chooses
   to run: RED-before-GREEN requires running the behavior's own tests inside
   that loop, and that is the mechanism working, not an exception to it.

6. **A negative result is a claim, and carries the same bar as a positive
   one.** "The search found nothing" is evidence about the search. "The file is
   unchanged" is evidence about the file, not about the failure. A number
   measured while you were perturbing the system is evidence about the
   perturbation. Before reporting an absence — no such test, no such caller,
   nothing tracked, not a regression — name the scope actually searched and why
   that scope is the population, or run a second strategy that would have found
   the thing if it existed: one tool, one pattern, one filter is a sample, not a
   census. And an unexplained signal is traced, never assigned an invented
   origin — "probably another session" is a story, not a cause.

## Cargento Project Contract

- **The canonical gate is not abbreviated.** Run the complete pre-PR suite in
  `AGENTS.md`, including docs sync, version-field parity, coverage, and native
  validators when their CLIs are installed. CI evidence is tied to the exact
  reviewed HEAD.
- **Runtime stays stdlib-only on Python 3.11+.** A new runtime dependency,
  interpreter-floor change, or platform-specific assumption is a design
  decision, not an implementation convenience.
- **One shared skill must remain portable.** Bundled skill Markdown cannot use
  host-specific resource variables, cache paths, or tool API names. Exercise
  affected behavior through every relevant harness contract.
- **Version fields are release-owned.** Feature PRs do not edit manifest
  versions. The tag-driven release workflow owns version movement.
- **Security invariants are load-bearing.** The dashboard remains bound to
  `127.0.0.1`, reads harness stores without mutating them, and never widens its
  documented project-read surface without explicit security review.
- **Docs ownership is explicit.** Update the owning file and link to it from
  other surfaces; run the repository's `sync-docs` development skill before
  proposing a PR.

## Stages

Every stage report opens with a one-paragraph TL;DR; raw command output,
full diffs, and re-derivations go in collapsed or linked sections. A report
that reads like a session transcript costs reading budget nobody spends.

### `backlog` — capture (this is the todo queue)

Any idea, rabbit hole, defect, or captain note enters as a seed task file:
title, `source`, one-paragraph description. Target cost: under two minutes.
Capturing a seed triggers NO design work — the gate is where the captain
curates what advances. A seed too vague for the captain to triage is the only
"bad" here.

#### Defect lane — skip `ideation` for a bounded fix

A known defect with a mechanical acceptance test does not need a design stage.
When **all four** hold, the FO advances `backlog → implementation` directly. The
verdict goes in the `lane` frontmatter field so it is queryable, and its
justification in the task body — a classification that lives only in prose gets
re-derived by re-reading every open task, which is the expensive way to learn
something already decided:

1. The root cause is already identified and cited at `file:line`.
2. Acceptance is mechanical — a test that fails before the fix and passes after.
3. It is a single seam: one surface, no cross-layer ripple, no schema change.
4. No design decision is open. If the fix has two defensible shapes, it is not
   in this lane.

Everything else still applies: RED-before-GREEN, the proof policy, the
validation stage, and the merge bar. **The lane removes a design stage, never
verification** — and a defect whose fix turns out to need a design decision
goes back to `ideation` rather than being decided inside implementation.

The lane removes the stage, never the stage's outputs. Ideation produces four
things later stages read back — a design determination, the ACs validation
checks against, the appetite and tolerance the correction-round budget measures
against, and the implementation dispatch sizing — so **the FO writes all four
at filing**: `design: trivial-pass` reasoned by the fourth condition above, one
AC that is the mechanical test named by the second, a one-line estimate with
its tolerance, and the sizing (for a bounded fix, one dispatch, unless the
filing says otherwise). That filing is
the lane's ideation of record; every clause elsewhere that says "the
ideation-declared X" reads it here. The lane's AC bar is that mechanical test
alone — a bounded fix restores behavior rather than delivering new value, so
the value-AC requirement does not apply, and a defect that needs one is not a
bounded fix and belongs in the main line. A defect filed missing any of the three is
not in this lane — it is an unfinished filing, and goes back for the same
reason an ideation gate without a design determination is returned unread.

Any of the four failing means the main line. When in doubt it is the main line;
the cost of over-shaping one fix is smaller than the cost of designing inside
an implementation stage nobody is reviewing for design.

### `ideation` — one gate for design, plan, and acceptance

The single judgment-heavy stage. Flesh out the problem, decide the approach,
define acceptance criteria and the test plan. The gate reviews all of it at
once. Discipline clauses:

- **The captain authors scope; the agent never infers it for a
  rubber-stamp.** For non-trivial tasks, open ideation by asking the captain
  a few short scope questions (what gets worse without this; the time
  budget; what to keep if forced to cut; what we are happily NOT doing;
  which assumption could be wrong) and compose Problem/Scope from the
  answers verbatim. Skip only with a stated small-scope reason.
- **Appetite is a forcing budget.** Record a time/scope budget in the task
  body, plus the deviation past which the work stops and gets re-cut rather
  than continuing. Those two numbers are the "ideation-declared estimate" and
  the "declared tolerance" the validation stage's correction-round budget
  measures each rework round against; a task that declares neither has nothing
  for that brake to read. When work is about to exceed it: cut scope (defer a sub-part to
  backlog) or park cleanly with re-enterable state and explicit open
  findings — never extend the budget silently, and never compress
  validation to land inside it. Size or budget variance is a drift signal
  to investigate, never a number to hit by padding artifacts or stripping
  tests.
- **The cheapest path that satisfies the AC is the default, and the gate is
  told which one it took.** Ideation answers two questions in the task body
  before choosing an approach: *what is the fastest path?* and *what is the
  smallest cut?* It then records the cheaper option it is taking, the more
  thorough option it is not taking, and why the difference is not needed to
  satisfy the AC. **Default to the cheap one.** This is a scope default, never
  a quality one — the proof policy, the AC bar, RED-before-GREEN and the
  validation stage are untouched, and "cheap" never means thinner evidence.
  The FO surfaces the choice at the gate in one line ("taking the cheap path:
  X; deferring Y") so the captain can override it before work starts. A cheap
  path taken silently is the agent authoring scope, which the clause above
  forbids — and an expensive path taken by default is the more common and
  more expensive mistake, because nobody is ever asked to approve it.
- **One-sentence pre-mortem.** Before the gate: "if this ships exactly per
  spec and still fails, the most likely cause is ___" — pick one of {wrong
  problem, criteria that pass without delivering value, wrong framing lens,
  hidden assumption, over-conviction}. This is an orthogonal
  future-failure check the AC rubric structurally cannot generate.
- **Design determination is mandatory, never skipped.** Every task records
  `design: required` (UI, contract, interface, schema, or visual surface
  affected — attach the concrete design decision: wireframe reference, API
  shape, before/after) or `design: trivial-pass` with a one-line reason. An
  ideation gate presented without a design determination is returned unread.
- **Reverse-recovery audit before any "build/add X"** (brownfield default):
  assume the abstraction may already exist. Layer-trace the path (UI →
  contract → handler → domain → persistence → readback) and classify each
  layer WORKING / EXISTS_BROKEN / STUB / MISSING with file:line. Greenfield
  is allowed only after proof of absence (multi-strategy, multi-language
  search) — the general bar for any absence claim is Proof Policy rule 6. A single broken seam means repair scoped to that seam, not a
  rebuild. Full procedure: `_mods/reverse-recovery-audit.md`.
  **Audit against the merge target** (fetch `origin/<trunk>` first), never
  only the working branch — a stale branch shows stale infrastructure, and
  a MISSING verdict read off it can be seven weeks wrong. Implementation
  re-verifies the audit's load-bearing MISSING claims against a fresh
  merge target before building, and escalates instead of building when a
  premise has collapsed.
  **Enforcement facts are read live, never inferred from repo files**:
  what CI actually requires (required checks, branch protection) comes
  from the platform API (e.g. `gh api .../branches/<trunk>/protection`),
  and a change touching a required job treats the job `name:` as that
  protection's identity — adding steps is identity-safe; renaming the job
  silently drops the protection.
- **AC are end-state properties with falsifiable proof.** Each AC names a
  property of the finished task (not a stage action) plus a `Verified by:`
  clause citing proof outside the task's own prose. At least one AC measures
  the end value the task exists for, against a baseline that can move the
  wrong way.
- **E2E-first acceptance.** When the task changes full-stack or user-visible
  behavior, at least one AC is verified by exercising the real flow end to
  end (browser drive, CLI invocation, service round-trip). Unit-only proof is
  insufficient for wiring claims. Skip only for docs/config/CI-only tasks,
  and record the skip reason.
- **Doc diff proposed here.** When the task changes behavior described by an
  owned Cargento document, ideation proposes the concrete doc diff
  (before/after wording) in the task body. The gate reviews it; implementation
  applies it; validation verifies behavior diff and doc diff landed together.
- **Spike the riskiest unverified mechanism first**, and record the result in
  the task body — or record "no spike needed: {proven mechanisms relied on}"
  so the determination is auditable.
- **Size the implementation dispatch here.** Default is ONE worker session —
  every extra dispatch pays a cold-start (re-reading the README, task body,
  and surrounding code). Split only when the estimate exceeds ~90 minutes,
  the work has 3+ independent behaviors, or parallel worktree lanes buy real
  wall-clock — and always split along behavior boundaries, each slice a
  complete RED→GREEN loop (never "tests in one dispatch, code in the next").
  Record the sizing decision in the task body so implementation inherits it.

### `implementation` — build in a worktree, test-first

- **RED before GREEN, with evidence.** For each behavior: write the failing
  test, run it, record the RED evidence in the stage report (test name +
  failure output digest), then write the minimum code to pass. GREEN without
  recorded RED is treated by validation as unproven — tests written after the
  fact to confirm existing code do not count.
- **Count new assertions against the RED output.** Every assertion added must be
  *able* to appear as a failure in that run. A case stops at its first failing
  assertion, so later assertions in the same case never execute — compare failing
  *cases* against the cases that should fail, and for the rest ask per assertion
  whether any RED run could reach it. One that would be green in RED holds in the
  pre-fix world too, so it is decoration, not evidence — rewrite it to pin the
  literal expected value, or delete it. This is the mechanical enforcement of
  "evidence must be able to fail"; the RED record aims at it but does not check
  it, and the tell is an added assertion no RED run can reach.
- **When you change a behavior, audit the tests that arrange the old one.** A
  suite that goes green after a behavior change can mean a fixture was silently
  re-purposed rather than that coverage held. Grep the suite for scenarios that
  *set up* the behavior under repair, and state per scenario whether the edit
  restored its original intent or quietly narrowed it.
- **A change that adds tests checks the CI job's remaining margin before
  pushing.** Job-level cancellation presents as a red check with **no failing
  assertion** — every suite reports passing and the step is killed anyway —
  which reads like a flake and invites a retry instead of a diagnosis. Thin
  margin is a gate-level disclosure, not a CI discovery.
- **RED and GREEN close in the same session, and commit together.** Never
  commit failing tests as a handoff contract for a later worker: an agent
  handed a red suite optimizes for "make it green", and will drift the
  implementation to fit a possibly-wrong test — or the test to fit the
  implementation — instead of delivering the behavior. The RED record is
  stage-report evidence; committed tests arrive with the code that passes
  them. If a session must stop mid-loop, the unfinished RED work stays
  uncommitted and the stage report says exactly where the loop stopped.
- **Scoped tests in the loop, full suite plus ripple at the exit.** During the
  build loop run only the tests scoped to the behavior under change (file,
  module, or tagged subset). Run the full suite exactly once, after scoped
  tests are green, as the stage-exit regression check — not on every
  iteration — and for a change to shared code, every affected validator and
  native platform check named by the canonical suite in `AGENTS.md`.
  **The exit condition is never "the reported error is gone."** That is a
  not-a-regression claim and Proof Policy 6 governs it: the one spec that named
  the bug was never the population. A failure surviving the exit run is written
  off as pre-existing only by the per-failing-line rule the validation stage
  states — never per file, never per impression.
- Minimal diff that satisfies the AC. No unrelated refactoring. Apply the doc
  diff approved at ideation in the same branch.
- The deliverable must be self-contained for a fresh validator: stage report
  says what was produced, where, and how to run it.

### `validation` — fresh eyes, adversarial by default

A fresh-context agent verifies the deliverable against the ideation AC. The
validator checks what was produced; it never finishes the work.

The gate is presented with a filled **evidence block** — one line of *specific,
falsifiable* evidence per item (presence of text is not the bar), and anything
left blank counts as not-done, never a silent pass. It records five lines —
`Lenses:` (the diff classification, and per fired lens its verdict and finding
count), `Diff coverage:` (the measured %), `Adversarial:`, `Cross-model:`,
`E2E:` — each naming what was actually run and what it returned.

**Any of them may be written `N/A — <why>`, never a bare `N/A`.** A skip
without its reason and a skip with one do not read alike, which is the same
rule this workflow applies to `escaped_defects_7d`. **The condition that
permits the skip lives in that field's own clause, and is not restated here**
— for `E2E:` that is the E2E-first acceptance clause at ideation; for the
rest, the validation clauses in this section. Only two are set here, because
nowhere else states them: `Adversarial: N/A — <why>` for a diff with no
behavioral guard to break, and `Diff coverage: N/A — no coverable source` when
the coverage gate reports none. `Lenses:` and `Cross-model:` are never `N/A`.
Scale changes how deep each item goes, never whether it runs — this block is
where an agent is tempted to convert "small" into "skipped", and small is not
a skip condition for any of the five. A gate presented without the block is
returned unread — the
same bar the ideation stage's design determination is held to.

- Reproduce each AC's `Verified by:` clause; report PASS/FAIL per criterion
  with actual evidence (command output, screenshots, on-disk state) — never
  the implementer's self-report. Same execution order as implementation:
  scoped checks per AC first, one full-suite run at the end — a full-suite
  failure outside the diff's blast radius is reported as context, not
  debugged by the validator.
- **Lens selection is mechanical, not a judgment call.** Classify the diff and
  fire every matching lens; a "touches none" is justified by naming the surfaces
  the diff *does* touch (so a reviewer can check the classification — not by an
  adversarial revert, which tests code, not a skipped lens). Correctness always
  fires; then, by what the diff touches: **security** (auth / permission / trust
  boundary) · **silent-failure** (error handling, input validation, fallbacks,
  swallowed errors) · **type-design** (a new or changed type) · **concurrency**
  (locks, async ordering, shared/mutable state) · **resource-lifecycle**
  (processes, handles, memory, unbounded growth) · **migration/back-compat** (a
  schema, wire-contract, or persisted-state change — does old data or an
  in-flight peer still work?). The independent cross-model gate (below) always
  runs and is recorded separately; it is not one of these lenses. For prose
  diffs (skills, agents, hooks-as-instructions), the correctness lens is
  **exercise-based**: actually invoke the changed skill/hook and observe
  behavior — a prose change reviewed only by reading is not reviewed. (Reviewer
  agents, fully qualified so the identifier can be dispatched as written:
  `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`,
  `pr-review-toolkit:type-design-analyzer`, `kc-pr-flow:tob-security-reviewer`.)
- **A documented guarantee is a claim, and gets the AC treatment.** When a doc
  diff states an absolute — "only", "always", "never", "exactly one" — name the
  input or edit that would falsify it, and check it, exactly as an AC names its
  falsifier. A guarantee the enforcement point does not make is a defect **in
  the doc even when the code is correct**, and a worse one than an undocumented
  gap, because the next reader builds on it. Validation verifies doc *claims*,
  not just doc presence.
- **Verify reviewer citations before acting on findings.** Check every cited
  `file:line` against the actual file — LLM reviewers fabricate plausible
  citations. If more than roughly a third of one reviewer's citations are
  wrong, discard that reviewer's entire round rather than triaging it. And
  when writing off a failure as pre-existing, prove it per failing line
  (blame against the change's commit range), never per file or surface — and
  never from a run whose conditions you were perturbing yourself.
- **Converge by naming residuals.** When a review round's findings stop
  being fixable defects and become a named class the chosen approach
  genuinely cannot solve, stop iterating: record the residual and its
  acceptance reason instead of opening another round. Chasing irreducible
  residuals is gold-plating dressed as rigor.
- **Cross-model gate before merge approval**: run one independent cross-model
  review of the diff. **Cross-vendor is relative to the model running the gate**,
  not a fixed list: pick the first available tool from a different vendor than
  the reviewing model — from a Claude session that is `codex` → `agy`, from a
  codex session it starts at `agy`. A lighter variant from the same family is
  not a second vendor and does not satisfy this. No single vendor is required,
  but skipping the second opinion entirely is not. **Unavailability is established by an
  attempted run that failed** (quota, auth, missing binary), never assumed —
  record which model ran the gate, which reviewer ran, and when a preferred one
  was skipped, the observed failure. A P1 finding is fixed or explicitly waived
  with a recorded reason at the gate — never silently dropped.
- Exercise the E2E AC in the real runtime. Whether the task owes one at all is
  decided by the E2E-first clause at ideation, not here.
- **Coverage is a ratchet, not a target.** The mechanical floor is the
  `fail_under` value currently configured in `pyproject.toml`, and repo-wide
  coverage never decreases from its measured baseline.
  A red coverage check is fixed or explicitly waived at the gate with a
  recorded reason. Coverage percent is never an AC by itself —
  RED-before-GREEN evidence proves behavior; the percentage only catches
  untested seams the TDD loop missed.
- **Adversarial spot-check.** For one or two core behaviors, make a
  claim-breaking edit (revert a guard, flip a boundary) in a scratch copy and
  confirm the suite goes red. A suite that stays green under a claim-breaking
  edit is a hole — route back with that evidence.
- **Live-CI red evidence short-circuits per step.** When an AC requires
  proving a required check actually fails on bad input, use a non-draft
  probe PR observed red on live CI — and plan one probe commit per step:
  steps within a CI job short-circuit, so a single red run proves only the
  first failing step, and proving N steps each go red takes N sequential
  probe commits. Close the probe PR without merging, delete its branch,
  and record the run URLs as gate evidence.
- Rejection routes back to implementation (`feedback-to`) with concrete,
  file-anchored fixes. A second consecutive rejection at this gate ends the
  loop and goes to the captain, per Gate Authority. **The trigger is the
  count, not the findings** — a cycle that closes every prior finding and
  immediately surfaces new ones on adjacent surfaces is the stronger stop
  signal, not a fresh start: the approach cannot hold the boundary, and the
  next cycle finds the next surface. Counting only repeated findings never
  fires on that case, and it is the common one.
- **Every correction round carries a budget record.** Each rework round
  appends one entry: the round's actual effort against the ideation-declared
  estimate, the deviation, and the findings disposition. Past the declared
  tolerance, record a design-reset decision (back to ideation to re-cut)
  before opening any further round — the counter-based escalation above and
  this budget-based brake are independent circuit breakers. A round whose
  findings are all declined records `0 fixed` with every decline named:
  "nothing was found" and "everything found was declined" must never read
  alike.
- **Rework re-anchors on the source requirement.** On any route-back, the
  rework agent re-reads the original requirement and diffs it against the
  current ACs before touching code — rework loops naturally optimize
  against intermediate artifacts and silently drop original constraints.
  Any dropped constraint is restored or explicitly justified first. **The diff
  runs the other way too: name every changed file no AC requires, and either
  delete it or state which AC it serves.** A rework loop adds machinery as
  readily as it drops constraints, and added machinery is the more expensive
  direction — it arrives with its own defects and its own review rounds, and
  each round it survives makes it look more load-bearing than it is.
- **One scope checkpoint before the first validation dispatch.** The FO sends
  the captain one line: files and lines changed, and **which changed files map
  to no AC**. Map each file to the AC it serves and report the unmapped ones —
  do not ask whether an AC names the file. ACs are end-state properties and
  rarely name an implementation path, so a name-matching check reports every
  legitimate file as unnamed while a stray one whose path happens to appear in
  an AC slips through.
  This is a notification with an optional veto, not a gate — the FO proceeds
  unless the captain answers. It exists because scope is the captain's alone to
  hold, and the cheapest moment to cut is after the diff is real but before
  review rounds have compounded on it. A round spent reviewing machinery nobody
  wants is paid twice: once to find its defects, once to fix them.

### `done` — terminal

Merge after a passed validation gate (merge policy: PR to `main`), set `completed` and `verdict`, archive the task. Record the
measurement ledger row (below) in the same transition.

- **Merge only on observed green CI for the exact HEAD.** A passing local
  suite, a static PR approval, or "CI was green earlier" never substitutes
  for a live CI run observed green on the commit being merged. A red or
  running check at merge time blocks the merge — no exceptions by memory.

## Continuation & handoff

Picking up an in-flight branch — a closed sibling tab, a session-limit resume, a
handoff record — does **not** inherit the prior agent's validation. Before
advancing: inventory what the prior agent left (committed **and**
uncommitted/WIP working-tree state), re-anchor on the source requirement,
re-classify the diff, and reconcile any upstream drift that landed on the trunk
during the hiatus. Those four are owed at whatever stage the work resumes. The
validation evidence block is **not** re-run by the resuming implementer — that
would be the self-report this workflow forbids; it is owed on entering or
re-entering `validation`, against a fresh merge target, by the fresh-context
validator that stage requires.
A prior agent's "mostly done / green tests / one review passed" is
a starting point to verify, never a validation to trust — the continuation frame
is exactly where a half-done validation gets silently inherited as complete.
Re-verify every inherited finding's load-bearing claim against the code, not the
prior narrative. This is the `Rework re-anchors on the source requirement` clause
with a broader trigger (any resumed work), not a separate workflow.

## Gate Authority

A gate is a decision point, not a status report. Who holds it depends on the
kind of decision, not on which stage it sits at.

| Seat | Holds | Examples |
|------|-------|----------|
| **Captain** | Direction and irreversibility | Scope authorship; what to work on next; schema / architecture / scope-cut / costly_no; accepting a documented residual against a red gate; any seat disagreement |
| **EM** (`ship-flow:science-officer-em`) | Bounded judgment on completed work | The ideation and validation verdicts — proceed / narrow / return / block |
| **FO** | Nothing adjudicative | Checklist accounting, AC-evidence presence, dispatch, merge mechanics, cleanup |

**Default: EM holds the gate.** The FO assembles the review — checklist
accounting, AC cross-check, reviewer findings — and routes it to EM for the
verdict. The FO neither renders the verdict itself nor forwards a completed,
findings-already-resolved stage to the captain for a rubber stamp.

**Auto-advance.** When a gate has zero Material findings, every AC carries
evidence, and the decision is reversible, EM approves and the FO advances
immediately. The captain is *notified in one line*, not asked. A captain who
wants it back says so; silence is not a gate.

**Escalate to the captain only when one of these holds — and name which:**

- The call is irreversible per Judgment Escalation below.
- Scope is being authored or re-cut. Only the captain holds scope.
- A Material finding survives EM review and changes what ships.
- A gate is red and the ask is to accept the residual on record.
- EM and FO disagree — that goes to the captain, never to a vote.
- Two consecutive rejected cycles closed at the same gate — see the validation
  stage's rejection clause. Unlike the bullets above it, this one fires on
  cycle count alone, whatever the findings were.

Anything else reaching the captain is over-escalation, and it costs more than
it protects: a captain pulled into six ceremonies per task stops reading the
two that mattered.

**Approval is scoped to the decision presented.** "The captain approved the
previous gate" is never authority for a later one.

**Speak consequence, not vocabulary.** A gate presented in the system's own
terms — a migration, a claim path, a corpus freeze — is not a decision the
captain can weigh; it is a request to trust the presenter. The tell is a
captain who answers "go with your recommendation" every time: at that point the
gate costs attention and returns nothing, and the seat has quietly moved back
to the FO without anyone deciding that it should.

Every escalation carries a plain restatement — literally "換句話說" — before it
asks for anything:

- **What breaks if this is wrong**, in terms of what a user or the team can no
  longer do. Not the mechanism; the consequence.
- **How expensive it is to reverse.** "Ships to production" and "one commit to
  revert" are different decisions and must not read the same.
- **What is actually being chosen.** Often it is narrower than the technical
  framing suggests — "restore something that was dropped by accident" is not
  "change how the system behaves", and the captain rules differently on each.

If the restatement cannot be written, the escalation is not ready: either the
FO does not yet understand the consequence, or there is no decision here and it
belongs to EM.

## Judgment Escalation

Irreversible calls — schema, architecture, scope-cut, costly_no, anything
merge-governing — are never self-adjudicated by the working agent.
**Merge-governing means a change to the merge rules themselves** — branch
protection, a required check, the merge policy — **not a gate verdict that
lets this one merge proceed.** A passed validation gate is the second kind, so
it stays inside the auto-advance rule above; reading it as the first kind
would make auto-advance dead for the only stage it matters at. Route to a
fresh-context engineering-judgment agent (`ship-flow:science-officer-em`) for
independent synthesis, add one cross-vendor pass (codex/gemini) when the call
is contested, and bring the captain a CONVERGED recommendation. The captain
rules; disagreement between seats goes to the captain, not to a vote.

## Canonical Docs Ownership

| File | Owner | Updated |
|------|-------|---------|
| `README.md` | Product front door, installation, skill inventory | When user-facing setup or capability changes |
| `AGENTS.md` | Repository contract and canonical pre-PR suite | When contributor or gate policy changes |
| `CONTRIBUTING.md` | Contributor journey and server design constraints | When development practice changes |
| `COMPATIBILITY.md` | Cross-harness/platform contract and Python floor | When compatibility changes |
| `SECURITY.md` | Security invariants and accepted exposure | When trust boundaries change |
| `cargento/skills/cargento/SKILL.md` | Shipped product surface | In the PR that changes agent-facing behavior |
| This README | Captain-approved revision | When ledger data says a clause needs tuning |

## Measurement Ledger

Every task that reaches `done` (or is abandoned after implementation started)
appends one row to `docs/dev/ledger.csv`:

```
task_id,slug,dispatches,rework_rounds,wallclock_hours,tokens_if_known,coverage,escaped_defects_7d
```

Record measurements at their natural boundary instead of reconstructing them:
the FO increments `dispatches` before handing control to a worker and appends
token usage when the harness exposes it. A worker that returns no usage records
`n/a`; it is not silently converted into a measured zero.

`escaped_defects_7d` starts as `pending` and is back-filled after the seven-day
window. The first ten complete rows form a prospective baseline for this
workflow. Until that cohort exists, the ledger supports observation only, not a
claim that this flow is cheaper or more effective than another workflow.

## Task Template

```yaml
---
id:
title:
status: backlog
source:
started:
completed:
verdict:
score:
worktree:
issue:
pr:
design:
lane:
---

## Problem

## Proposed approach

## Design determination

`required` (attach decision) or `trivial-pass — <reason>`.

## Acceptance criteria

**AC-1 — <end-state property>.**
Verified by: <reproducible check outside this file>. Falsified by: <the edit that would flip it>.

## Test plan

## Doc diff

<before/after wording for the owning Cargento document, or "none — no described behavior changes">

## Out of scope
```

## Commit Discipline

- Status changes commit at dispatch and merge boundaries (binary-owned).
- State commits are path-scoped per entity in the state checkout — never bare `git add -A`.
- Implementation commits land on the worktree branch; merge only after the validation gate passes.
