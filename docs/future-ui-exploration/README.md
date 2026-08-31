---
commissioned-by: spacedock@0.27.2
entity-type: design_experiment
entity-label: experiment
entity-label-plural: experiments
id-style: slug
state: .spacedock-state
stages:
  defaults:
    worktree: false
    concurrency: 1
  states:
    - name: framing
      initial: true
      gate: true
    - name: reconnaissance
    - name: prototyping
      worktree: true
    - name: crucible
      worktree: true
      fresh: true
      gate: true
      feedback-to: prototyping
    - name: accepted
      terminal: true
  transitions:
    - from: crucible
      to: prototyping
      label: evidence supports the direction but exposes a material correction
    - from: crucible
      to: framing
      label: evidence invalidates the underlying interaction or information model
    - from: crucible
      to: accepted
      label: captain and first officer judge the direction genuinely strong
---

# Future UI Exploration

This workflow explores bold ways for Cargento to give people a straightforward understanding of what is happening across all of their harnesses and sessions. It treats the Next UI as a command surface rather than an inventory: the overall situation, the work that matters now, current execution, the next action, and captain responsibility must lead; evidence and detail remain reachable without competing with those facts.

The durable integration branch is `feat/future-ui`. Every product checkpoint produced by this workflow stays on that branch. Nothing in this workflow targets or merges into `main`.

## File Naming

Each experiment lives in a folder named with a lowercase, hyphenated slug. Its canonical state file is `index.md`; screenshots, review briefs, and comparison artifacts may live beside it when the experiment needs them.

## Schema

Every experiment has YAML frontmatter with the following fields.

| Field | Type | Description |
|---|---|---|
| `id` | string | Blank for `id-style: slug`; the slug is the durable identity. |
| `title` | string | Human-readable experiment name. |
| `status` | enum | One of `framing`, `reconnaissance`, `prototyping`, `crucible`, or `accepted`. |
| `source` | string | The request, debrief, observation, or prior round that produced the experiment. |
| `started` | ISO 8601 | When active work began. |
| `completed` | ISO 8601 | When the captain accepts the direction. |
| `verdict` | enum | `PASSED` only after the captain accepts the direction. |
| `score` | number | Optional priority from 0.0 to 1.0. |
| `worktree` | string | The dedicated checkout used after the experiment reaches a product-changing stage. |
| `issue` | string | Optional GitHub issue reference. |
| `pr` | string | Optional PR reference; never a PR targeting `main`. |

## Stages

### `framing`

The experiment is in framing while the crew turns the underlying ask into a bold, falsifiable design bet without assuming the current dashboard structure should survive.

- **Inputs:** The 2026-08-27 project-cockpit debrief, current `?next=true` UI, captain direction, available design records, and known source limitations.
- **Outputs:** A concise bet; the user questions it should answer; the command-risk baseline; explicit non-goals; and evidence that would invalidate the model rather than merely suggest polish.
- **Good:** The frame attacks the information or interaction model, names what should lead, and permits a materially different UI.
- **Bad:** Treating the work as incremental cleanup, preserving existing regions by default, or defining success as visual preference.
- **Gate content:** Show the bet, why it could materially improve comprehension, what it risks, how it will be falsified, and what the three harnesses must exercise.

### `reconnaissance`

The experiment is in reconnaissance while Codex, Claude Code, and AGY generate and inspect real activity against the current Next UI.

- **Inputs:** The approved frame, live dashboard at `http://127.0.0.1:4553/?next=true`, exact session identities, live APIs, relevant source, and the registered interaction origins available to each harness.
- **Outputs:** One observed session from each harness; screenshots of the project overview and a session drill-down; a fact-versus-inference inventory; and findings ranked by comprehension or command risk.
- **Good:** Each harness contributes distinct observable evidence, missing sources remain explicit, and the record distinguishes UI failure from unavailable underlying data.
- **Bad:** Mock-only evaluation, reviewing a static screenshot without live state, letting reviewer-created activity silently replace the session under study, or treating an empty signal as proof that no captain action exists.

### `prototyping`

The experiment is in prototyping while the crew implements the strongest candidate on `feat/future-ui`, starting from the accepted checkpoint of the prior round.

- **Inputs:** The approved frame, reconnaissance evidence, current branch bytes, prior crucible findings, and the repository's frontend byte-pin contract.
- **Outputs:** A coherent candidate at `?next=true`; one durable checkpoint per accepted correction; focused tests; updated byte pins derived from assembled assets; and before/after captures tied to exact candidate bytes.
- **Good:** Large structural bets are welcome, the lede is legible in a five-second scan, project overview and session drill-down answer different questions, and semantic claims remain source-bound.
- **Bad:** Adding panels instead of choosing priority, burying command truth under provenance, implying causal links the data does not establish, changing unrelated shipped UI, or running competing full suites in parallel.

### `crucible`

The experiment is in crucible while fresh reviewers try to disprove that the candidate gives users a truthful, immediate understanding of all harnesses and sessions.

- **Inputs:** The live candidate, fresh screenshots, current APIs, source and renderer fixtures, exact three-harness session evidence, focused test results, and every unresolved finding from the prior round.
- **Outputs:** Independent reviews covering visual hierarchy, information architecture, command truth, cross-harness comprehension, session drill-down, accessibility, and adversarial states; reproduced material findings; a disposition for every finding; and a recommendation to revise, reframe, or accept.
- **Good:** Reviewers are fresh, every material claim is exercised at the layer where it can fail, accepted findings are implemented before another review, and disagreement is resolved by reproduced evidence.
- **Bad:** Reviewer attachment to the prior design, ranking unsupported findings by confidence, optimizing style after command truth is already complete, or claiming convergence because tests are green.
- **Gate content:** Lead with the recommendation. Show whether a person can quickly answer overall situation, current assignment, execution state, current activity, next action, and captain responsibility; name every material uncertainty and its owner; then ask the captain to revise, reframe, or accept.

### `accepted`

The experiment is accepted only when the captain and first officer both judge the direction genuinely strong. Acceptance records the exploration outcome on `feat/future-ui`; it does not authorize a merge to `main`.

- **Inputs:** A captain-approved crucible verdict and the exact accepted branch checkpoint.
- **Outputs:** A terminal record linking the accepted checkpoint, evidence, known limits, and remaining product decisions.
- **Good:** The accepted result satisfies the comprehension outcome and preserves honest scope and provenance.
- **Bad:** Terminalizing because a schedule expired, a fixed iteration count was reached, or reviewers ran out of findings.

## Workflow-specific rules

- **Integration branch invariant.** `feat/future-ui` is the only durable product branch this workflow advances. Product commits and accepted correction checkpoints remain there. No workflow command, PR, or terminal action may target `main`.
- **One rolling experiment.** The pilot is one long-running direction so all work touching `cargento_runtime/web/next/` stays on one conflict surface. New hypotheses become recorded rounds inside the experiment unless the captain explicitly commissions another independent direction.
- **Large bets are in scope.** A round may replace the information architecture, navigation model, visual hierarchy, or session interaction model. Compatibility with the current Next layout is not a value criterion.
- **Lede-first stop criterion.** The primary frame must expose assignment, execution, next action, and captain state without opening Evidence. It must also make project scope and current session activity obvious. Once those facts are truthful and unmistakable, another round needs a material comprehension risk rather than a style preference.
- **Three-harness evidence.** Reconnaissance and crucible must include observed Codex, Claude Code, and AGY sessions. A harness that cannot produce evidence is reported as a source limit, never silently replaced by a mock.
- **Sequential review loop.** A fresh antagonistic review follows every accepted correction. Each round begins from the prior accepted checkpoint; concurrent product edits are forbidden, while independent read-only lenses may run in parallel.
- **External proof.** Screenshots establish hierarchy, live APIs and source establish semantic claims, adversarial fixtures test missing or conflicting data, and focused tests protect behavior. A prose assertion cannot prove runtime comprehension.
- **Contention discipline.** Check sibling worktrees before trusting failures. Run the full suite once and serialize it; retry known load-sensitive modules alone before classifying a failure as a regression.

## Workflow State

View the workflow with:

```bash
spacedock status --workflow-dir docs/future-ui-exploration
```

## Experiment Template

```yaml
---
id:
title: Experiment name
status: framing
source:
started:
completed:
verdict:
score:
worktree:
issue:
pr:
---

## Design bet

A bold, falsifiable claim about how Cargento can make cross-harness and session state easier to understand.

## Baseline and command risk

What users can and cannot understand today, with reproducible evidence.

## Method

How Codex, Claude Code, and AGY will exercise the candidate and how fresh antagonistic review will challenge it.

## Acceptance criteria

Each criterion names a user-visible property of the finished command surface and a check outside this file that can fail.

## Iteration record

One entry per implemented and reviewed checkpoint: hypothesis, evidence, correction, disposition, and exact branch commit.

## Known limits

Sources or authority the UI cannot honestly recover.

## Out of scope

What this experiment deliberately does not attempt.
```

## Commit Discipline

- Commit workflow-state changes at dispatch and gate boundaries.
- Commit each accepted product correction on `feat/future-ui` before the next antagonistic review.
- Never create or merge a PR from this workflow into `main`.
