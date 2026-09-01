---
commissioned-by: spacedock@0.27.1
entity-type: roadmap_issue
entity-label: issue
entity-label-plural: issues
id-style: slug
state: .spacedock-state
stages:
  defaults:
    worktree: false
    concurrency: 2
  states:
    - name: selection
      initial: true
    - name: triage
      gate: true
    - name: implementation
      worktree: true
      context-sections:
        - Review-finding disposition
    - name: review
      worktree: true
      fresh: true
      feedback-to: implementation
      gate: true
      context-sections:
        - Review-finding disposition
    - name: done
      terminal: true
    - name: recorded
  transitions:
    - from: selection
      to: triage
      label: picked
    - from: triage
      to: implementation
      label: drafts approved at the gate
    - from: implementation
      to: review
      label: PR opened
    - from: implementation
      to: recorded
      label: no delivery — the cycle's product was a Linear record change, not code
    - from: review
      to: done
      label: merged
---

# Burn down the Cargento Visibility 2x2 Roadmap

One roadmap issue at a time, from picked to merged, with the Linear records left true afterwards.

The project is **Cargento: Visibility 2x2 Roadmap** in Linear (team `DRC`):
<https://linear.app/recce/project/cargento-visibility-2x2-roadmap-c43e013de860/overview>. Each
issue on that board is one entity here. The workflow runs until the board is empty.

This workflow does not invent its own picking rules, its own build discipline, or its own
reconcile list. Those already exist and are owned elsewhere: the `burndown` skill owns picking and
reconciling, `recce-dev:linear-deep-dive` owns issue analysis, `superpowers:test-driven-development`
owns the build, and **AGENTS.md, "Pre-PR Checks"** owns the gate. What this workflow adds is the
part none of them own — a durable place for one issue's journey to sit between sessions, an
adversarial pass over the issue text itself before anyone builds against it, and a review whose
depth is chosen rather than assumed.

## Why the issue text gets reviewed before the code does

This board has been running long enough that its issues have accumulated history: approaches that
were tried and abandoned, scores from a panel that has since been re-run, decisions recorded in
prose that a `blockedBy` edge still contradicts. An agent handed a stale issue builds the stale
thing, confidently, and every check downstream passes because nothing downstream reads the issue.

So `triage` is a real stage with a real gate, not a formality. It is the only point where the
thing being built is compared against what the project currently wants.

## File Naming

Each issue lives as a flat markdown file named for its Linear identifier: `drc-4029.md`. Use the
folder form `drc-4029/index.md` only when an issue produces sibling artifacts (a capture, a
transcript, a comparison table) that belong beside the tracker.

The slug is the identity. Linear already assigns these numbers and is the single writer of them,
so this workflow does not mint IDs of its own — a generated ID would be a second counter competing
with the one that already exists.

## Schema

Every issue file has YAML frontmatter. Fields are documented below; see **Issue Template** for a
copy-paste starter.

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Optional. `id-style: slug` means the filename slug (`drc-4029`) is the effective ID. |
| `title` | string | The Linear issue title, verbatim. Changed here only when it is changed in Linear. |
| `status` | enum | One of: selection, triage, implementation, review, done, recorded. `done` is terminal; `recorded` is parked. |
| `source` | string | Always the Linear issue URL. This is the record of where the truth lives. |
| `started` | ISO 8601 | When active work began |
| `completed` | ISO 8601 | When the issue reached terminal status |
| `verdict` | enum | PASSED or REJECTED — set at review. Left **empty** on an entity that parks at `recorded`: a cycle whose product was a Linear record change was neither delivered nor rejected, and stamping either would be a false record. |
| `score` | number | Release-row weight, 0.0–1.0. A sort hint, **not** the pick order — see **Scoring**. |
| `worktree` | string | Worktree path while a dispatched agent is active, empty otherwise. Set on first dispatch into a worktree stage, sticky across non-terminal advancement, cleared at terminal merge. |
| `issue` | string | GitHub issue reference, only when a mirrored GitHub issue actually exists. Usually empty. |
| `pr` | string | GitHub PR reference (e.g. `#57`). Set by the `pr-merge` mod when the PR opens. |
| `mod-block` | string | Pending mod-declared blocking action, format `{lifecycle_point}:{mod_name}` |
| `linear-status` | string | The Linear state as last observed (`Backlog`, `Todo`, `In Progress`, `Ready for Review`, `Blocked`, `Done`). A cache for selection, never authority. |
| `milestone` | string | The owning Linear milestone name, or empty. The milestone `triage` reviews and `done` reconciles. |
| `release` | string | The `release:*` label row: `r1`, `r2`, `r3`, `later`, or empty. Drives rule 2 of the pick order. |
| `estimate` | string | The Linear estimate (`XS`/`S`/`M`/`L`/`XL`), or empty. |
| `reconciled` | ISO 8601 | When the post-merge Linear reconcile completed. Written and committed **before** `merge guard` terminalizes. Empty on an archived entity with `pr` set means the reconcile was interrupted. |

### ID Style

`id-style: slug`. The `id` field is optional and left blank; the effective ID is the slug, which is
the lowercased Linear identifier. `status --next-id` is not applicable.

```yaml
id-style: slug
```

## Scoring

`score` is the release-row weight and nothing more: `r1` 0.9, `r2` 0.7, `r3` 0.5, `later` 0.2,
unlabeled 0.6. It exists so `spacedock status` sorts into something readable.

**It is not the pick order.** The pick order is the `burndown` skill's six lexicographic rules, and
no single float can encode them — a float that appeared to would be a confidently wrong number, of
exactly the kind this project has been burned by before. `selection` applies the rules against a
live Linear fetch. When the rules and this number disagree, the rules win and the number is stale.

Unlabeled issues sit at 0.6 rather than 0 because a probe or a bug carries no `release:*` label and
ranks on what it settles, not on a label it was never given.

## Stages

### `selection`

An issue sits in `selection` when it is on the board and has not yet been picked. The stage's work
is choosing which one leaves, and reconciling the board against Linear before choosing.

- **Inputs:** A live Linear fetch of the project's issues, their states, labels, estimates,
  milestones and `blockedBy` relations. The `burndown` skill's pick rules. The existing entity
  files. `docs/visibility-2x2/items.json` for panel scores **only** — its `state` fields are
  deliberately stale and are the dated record of what was scored, never what shipped.
- **Outputs:**
  - **Before anything else:** any **non-archived** entity with `pr` set and `reconciled` empty is an
    interrupted post-merge reconcile. Finish it before picking. An issue whose code merged but whose
    Linear record still reads open is otherwise picked a second time and rebuilt.
  - **An *archived* entity in that shape cannot be repaired at all** — `status --set` refuses an
    archived entity as read-only, so `reconciled` has exactly one window and `merge guard` closes it
    permanently. Do not try to stamp it. Confirm the reconcile happened by reading the **receipt
    comment on the Linear issue**, which is why `done` requires one, and move on. Measured 2026-08-28
    on `drc-4274`, the first entity this workflow merged: its reconcile ran correctly but *after* the
    guard, so it is archived unstamped and its receipt is the proof. A known false positive of this
    query, not an outstanding task.
  - Board reconciled next, before any pick: an entity created for every open project issue that
    has none, and any entity whose Linear issue is now `Done` or `Canceled` noted as closed outside
    this workflow. A pick made against a stale board is a pick of the wrong thing.
  - An entity already parked at `recorded` is handled by reading its Linear state, per the table in
    that stage — left alone while `Blocked`, noted while `Done`, moved back here once open and free. When that
    blocker closes, the issue leaves `Blocked` in Linear and the entity becomes an ordinary
    candidate again with no special handling — move it back to `selection` at that point rather
    than filing a second entity for the same issue.
  - `linear-status`, `release`, `estimate` and `milestone` refreshed on the surviving entities from
    the fetch, so the cached fields are not lying to the next stage.
  - The pick and its reasoning stated in **one line** before anything is touched, naming which rule
    decided it.
  - Every candidate dropped for an open blocker named, with the blocker. A decision issue that is
    not `Done` is an open blocker even when its body records the call — check `blockedBy`, not prose.
  - Exactly one issue advanced to `triage`.
  - When no candidate survives the rules, say which of the two endings it is: **board empty** (every
    project issue `Done` or `Canceled` — report the burndown complete, with the count worked and the
    date range) or **board blocked** (candidates remain but every one is held by an open blocker —
    name each blocker and what it gates, because that is a decision backlog, not a finish). Silence
    is not a valid ending; a stalled loop and a finished one look identical from outside.
  - An entity unpickable by state rather than by rank — `Blocked` in Linear, or already `Ready for
    Review` — is reported once per cycle in a single line and not re-reasoned. Re-deriving the same
    "not eligible" every cycle is noise that hides a real change of state when one happens.
- **Good:** The reasoning is falsifiable — it names the rule and the losing candidate, so a reader
  can disagree with a specific step. Promotion out of a later release row happens only when
  something the promoted item gates sits in the row being worked, and says which item that is.
- **Bad:** Picking from the entity files without re-fetching Linear, because issues move outside
  this session. Reading `items.json` for what has shipped. Treating a decision issue's recorded
  prose as settling the gate its `blockedBy` edge still holds. Advancing more than one issue at a
  time without having read **Parallel Work** in `AGENTS.md` first.

### `triage`

The picked issue is adversarially reviewed — the issue and its owning milestone both — and a rewrite
is drafted so that what they say is what the project currently wants. The drafts stay in this entity
until the gate approves them; `implementation` writes them to Linear as its first action. This is
the only stage whose product is a change to the roadmap records rather than to the code.

- **Inputs:** The live Linear issue body, its comments, its relations, its labels; the owning
  milestone's description; the project overview's "As of" block; the repository as it stands today.
- **Outputs:**
  - An adversarial read of the issue against the current codebase, answering: is the problem still
    real, is the described approach still the one that fits, does any part of the body describe a
    state that no longer exists?
  - The original issue body and the owning milestone description copied **verbatim** into this
    entity under `## Linear edits made`, before anything else, as the pre-edit record.
  - The rewritten issue body **drafted into this entity, not written to Linear.** Superseded content
    is **demoted to a dated historical section, not deleted** — the record of what was believed and
    when is what makes a later reader able to trust the rest.
  - The corrected milestone description drafted the same way, wherever the issue's rewrite made the
    existing one false.
  - Acceptance criteria written into this entity as end-state properties with `Verified by:`
    clauses, each split as **offline** (a test, command, or on-disk state a fresh agent reproduces)
    or **interactive** (needs a human or a live drive). The split is declared here, at the gate, so
    a plan to build a harness that automates an interactive AC is visible before the harness exists.
  - An expected surface estimate with tolerance, and the semantics the change may move. **Cost the
    oracles separately from the runtime, and check whether any existing required check compels a new
    test file before declaring** — an import-graph allowlist that rejects a new module, a protocol
    fake that must be satisfied, a documentation drift-guard. Measured on DRC-4037's PR 1, where the
    runtime landed at exactly the declared figure across exactly the declared files while tests came
    in at 9 files and +541 against 6 declared, three of them compelled rather than chosen. The
    estimate was not wrong about the work; it was wrong about what the repository's own contracts
    would demand of it. An overrun of that shape is accepted once — if a later one repeats it, fix
    the estimating method rather than stretching the tolerance again.
- **Good:** The rewrite is shorter than what it replaced and a stranger could build from it. The
  historical section is dated and labelled as history. Every claim about the current code was
  checked against the code rather than against the issue's own prose.
- **Bad:** Deleting history instead of dating it. Widening scope to make the issue feel complete —
  the board's estimates assume the narrow reading. Writing acceptance criteria whose only proof is
  a review of this entity's own prose. Proceeding when the issue turns out to need a product
  decision nobody has filed: file the decision issue, link it as a blocker, and send this back to
  `selection` instead of guessing. Writing the rewrite to Linear before the gate approves it — the
  issue and its milestone are records other people read, so an unapproved rewrite sitting on the
  board is a false statement of what the project wants, and rejecting it afterwards does not
  un-publish it.
**When the picked issue is itself a decision** (a `DEC-N` item), the shape changes and this stage
becomes the only one that does real work. `triage` does not answer the question — it makes the
question answerable, and **the gate is where the captain rules.** Its product is: the question
stated in one sentence a person can say yes or no to; the evidence that bears on it, gathered from
the code and from live stores rather than from the issue's own prose; each available answer with
what it costs and what it forecloses; the precedent, and honestly whether the precedent settles it;
and what is already settled and is not being reopened. Recommend one answer — the captain is owed a
recommendation, not a menu — but never record the decision as made. `implementation` writes the
captain's ruling into Linear, closes the issue, and moves whatever it gated to `Todo`; the entity
then parks at `recorded`. A decision issue must not be sent back to `selection` for want of a
decision: it *is* the decision, and that would be a loop.

- **Gate content:** Show the captured original against the drafted rewrite, the drafted milestone
  correction, what was demoted to history and why, the acceptance criteria with their
  offline/interactive split and each `Verified by:` clause, the expected surface and tolerance, and
  the approach chosen with the simplest rejected alternative and the reason it cannot deliver the
  value. **Nothing has been written to Linear yet — this gate authorizes that write.** For a
  decision issue, show instead the one-sentence question, the evidence for and against each answer,
  what each answer costs, whether the precedent settles it, and the recommended answer — **and this
  gate is where the captain rules, not merely where a draft is approved.**

### `implementation`

The rewritten issue is approved and gets built in a dedicated worktree on its own branch.

- **Inputs:** The approved entity body and its acceptance criteria. The repository. **AGENTS.md**,
  in particular "Pre-PR Checks", "Parallel Work" and "Code Comments".
- **Outputs:**
  - **First action:** the drafts the gate approved written to Linear — the issue body, and the
    owning milestone description. Nothing else in this stage starts until that write lands, so the
    board and the branch describe the same intent from the moment work begins.
  - `recce-dev:linear-deep-dive` run for this issue and **stopped at step 6, Propose Approach** —
    its classification, key files and risks are used; its own workflow past step 6 is not continued,
    because this stage owns what happens next.
  - The failing test written first and **watched to fail for the right reason**. A test that passes
    the moment it is written is testing what already worked.
  - The canonical pre-PR suite run from **AGENTS.md, "Pre-PR Checks"** — read from there, not from
    a copy, because a local copy is how someone passes locally and fails the required check.
  - `sync-docs` invoked, its doc updates committed onto this same branch. It is a step of the gate,
    not an optional extra.
  - The actual surface measured against the triage estimate **before the PR opens**:
    `git diff --numstat "$(git merge-base main HEAD)"..HEAD`, reported as files and LOC versus
    declared, with the percentage. Beyond the declared tolerance, stop and put it to the captain as
    a design reset rather than opening the PR. An estimate exceeded silently is how a narrow issue
    becomes a wide one without anyone deciding to widen it, and a tolerance nothing measures is
    decoration.
  - A PR opened whose body starts `Implements [DRC-####](url) — <issue title>` and carries a
    `## Verification` section naming what was run and what it said. `Closes #NNNN` only when a
    mirrored GitHub issue actually exists, one line per issue, never comma-separated.
  - The diff reviewed **in the worktree before the PR is opened**. Reviewing after means every PR
    runs CI twice — green, blocked by review, fixed, green again — at roughly fifteen minutes of
    pure waiting per PR, avoidable by reordering two steps.
- **One issue per branch, deliberately.** `burndown`'s rule wins over **AGENTS.md**'s "One PR per
  conflict surface, not one per issue" here, and the choice is recorded rather than inherited: this
  workflow's unit of merge risk is also its unit of Linear reconcile, and a PR spanning two issues
  cannot cleanly perform the post-merge reconcile for either. The cost AGENTS.md prices — a review,
  a fix round, a CI cycle and a merge serialization per extra PR — is real and accepted. The hard
  constraint survives regardless: exactly one in-flight PR may touch `cargento_runtime/web/`.
- **Good:** The change is the narrow reading of the issue. Commits are DCO signed off. Comments
  record decisions — why not the obvious alternative, what was measured, what was rejected — and
  never restate the line below them.
- **Bad:** Editing a version field; the tag-driven Release workflow owns them and `version-guard`
  fails any PR that touches one. Widening scope. Filing a second problem as part of this branch
  instead of filing it as its own issue. Believing a failure in `test_http_api`, `test_page`,
  `test_lifecycle` or `test_quota` without re-running that module alone — concurrent suites
  manufacture those, and a load average above about 10 makes it near-certain.
- When a finding arrives, follow `## Review-finding disposition`: investigate read-only, preserve
  its evidence, propose materiality, ownership and disposition, and obtain distinct FO
  authorization before any candidate edit, commit, or reviewer rerun.

### `review`

A fresh agent that did not build the change reviews the PR at a depth it chooses. **It observes and
verifies; it does not edit.** Confirmed material findings route back to `implementation` over the
`feedback-to` edge, which fixes them and returns the PR for re-review. `fresh: true` buys a reviewer
with no stake in the change, and that is spent the instant it edits — from the first edit onward it
would be reviewing its own work.

- **Inputs:** The PR, its diff, its CI state, the acceptance criteria from `triage`, and
  **AGENTS.md, "Calibrating Effort"**.
- **Outputs:**
  - **Review depth chosen from the diff and stated up front**, per the Calibrating Effort table:
    self-verify for a change with no user-visible behaviour that nothing calls yet; full adversarial
    for security, credential handling or data loss; two lenses plus an arbiter for everything else,
    including anything touching `cargento_runtime/web/` byte pins, `SKILL.md` or `config.py`.
    Uniform depth is the failure this table exists to prevent — it cost 35 agents and 6.9M tokens
    for 10 blocking findings on one measured run.
  - **An arbiter that reproduces findings rather than ranking them.** On the measured run it refuted
    13, including two blockers the orchestrator had asserted himself. Without that pass the lens
    count has to rise to compensate, which is the expensive direction.
  - Each acceptance criterion reproduced from its `Verified by:` clause rather than trusted from
    the implementation's self-report. Interactive criteria are settled by a live drive or by the
    captain, never by new automation built here.
  - **Copilot inline review comments read, in addition to top-level reviews** (AGENTS.md, PR
    Workflow). A review that reads only top-level is how an inline finding gets merged past.
  - Confirmed material findings routed back to `implementation` through the `feedback-to` edge with
    their evidence, classification and authorized disposition transported unchanged — never
    re-triaged, and never fixed here.
  - CI green on the **current head**. After any sibling merge this PR goes `BEHIND` and needs
    `gh pr update-branch` plus a **full CI re-run**; the re-run is the point, because the previous
    green belonged to a superseded head.
  - A GO or NO-GO verdict with the findings that produced it.
  - On GO, the worktree removed **before** the branch is deleted. `gh pr merge --delete-branch`
    fails while a worktree still holds the branch, and the tempting unstick — `git reset --hard` in
    the main checkout — destroyed uncommitted work here once. Remove the worktree, then merge.
- **Good:** The depth is justified by the diff before the review starts, not after. Findings that
  are correct but disproportionate are recorded as declines rather than dutifully fixed. A verdict
  cites what was reproduced.
- **Bad:** Trusting a green CI run that finished before the last push — check `mergeStateStatus` is
  `CLEAN` and that the checks belong to the current head. Trusting `git merge-tree`'s
  three-argument form to reveal conflicts; it did not, and a real conflict followed. Promoting a
  deferred finding into this PR — file it; promoting buys another implement-and-CI round for
  something already judged not worth blocking on, and four promotions cost about an hour once.
  Resolving a frontend byte-pin conflict textually: recompute from the assets, because each side is
  correct for a tree that no longer exists. Editing the PR branch from this stage at all — a fix
  belongs to `implementation`, and a reviewer that has edited can no longer say the change was
  checked by someone who did not write it. Reading only top-level reviews and calling the review
  complete.
- When a finding arrives, follow `## Review-finding disposition`.
- **Gate content:** Show the chosen review depth and the diff property that justified it, the
  findings under their disposition labels with what the arbiter reproduced or refuted, each
  acceptance criterion with the evidence reproduced for it, the CI state and the head SHA it belongs
  to, `mergeStateStatus`, whether Copilot left inline comments and what became of them, and the
  GO/NO-GO verdict. This gate authorizes the merge; on rejection the findings route to
  `implementation` rather than being fixed here.

### `done`

Terminal. The PR is merged — tracked on the `pr` field by the `pr-merge` mod and finalized by
`spacedock merge guard`, which terminalizes and archives atomically. Reached by a real merge, never
by a manual flag flip.

**The merge is not the end of the work.** `## Post-merge Linear reconcile` below is required and
runs at merge detection. An issue whose code landed and whose Linear records still say otherwise is
the specific failure this workflow exists to stop.

**Order, and it is not optional.** The merge lands, then the reconcile runs, then `reconciled` is
stamped, and only then is `merge guard` invoked. The guard terminalizes **and archives** in one
locked write, and an archived entity is read-only — so calling it first makes `reconciled`
permanently unsettable and leaves a false positive in `selection`'s guard forever. The tempting
wrong order is the natural one, because the guard is what confirms delivery. Resist it. Learned by
getting it wrong on `drc-4274`.

- **Inputs:** The merged PR and its merge commit, the entity's acceptance criteria, the owning
  milestone description, the project overview's "As of" block, and the closed issue's `blocks`
  relations.
- **Outputs:**
  - All five edits in `## Post-merge Linear reconcile`, in order.
  - A comment posted on the Linear issue naming all five edits and the merge commit. This is the
    **external receipt**: it lives in the system the reconcile is about, it survives the entity
    being archived, and it is visible to someone who never opens this workflow.
  - `reconciled: {ISO 8601}` written to the entity frontmatter and committed **before**
    `merge guard` terminalizes. `merge guard` terminalizes and archives atomically, so an entity
    that reaches the archive with `pr` set and `reconciled` empty is an interrupted reconcile — and
    it is recoverable only because the field is absent. Without it, a session that dies between the
    merge and step 3 leaves an issue whose code shipped and whose Linear record still reads open,
    and the next `selection` cycle picks it again and rebuilds it.
- **Good:** All five edits made against the merged state, not against the pre-merge intent. The
  milestone edit names what actually shipped. Step 5 leaves closed-to-closed edges alone.
- **Bad:** Reporting the issue closed before the receipt is posted. Sweeping a closed-to-closed
  `blocks` edge — that turns a satisfied dependency into no dependency, which is a different and
  less true statement than the one the edge was making.

### `recorded`

**Parked, not terminal.** The cycle's deliverable was a change to the **Linear record** rather than
to the repository. Two shapes reach it, and both are real outcomes rather than failures:

- **Escalated.** `triage` found the issue needs a decision nobody had filed. `implementation` filed
  the decision issue, added its `blocks` edge, rewrote the body and corrected the milestone. The
  issue stays open in Linear as `Blocked`.
- **Decided.** The issue *was* the decision. `triage` sharpened the question and assembled the
  evidence, **the captain ruled at the gate**, and `implementation` wrote that ruling into Linear,
  closed the issue, and moved whatever it gated to `Todo`. The issue is `Done` in Linear.

**Why parked rather than terminal**, measured on DRC-4029 rather than assumed:

- Terminal is the wrong claim for the escalated shape. A blocked issue is waiting on a decision, not
  done, and `terminal` would say the cycle ended forever.
- Terminal is mechanically hostile for both. `status --set` treats a terminal status **and clearing
  `worktree=`** as terminal updates, and a workflow declaring a `merge:` hook refuses any terminal
  update with no `pr` and no `mod-block`. So a terminal end state could only ever be reached with
  `--force`, on every no-delivery cycle — and this board carries five open decision issues, so those
  recur. A normal path that needs `--force` is a design error, not a fact of life.
- The scheduler leaves a parked entity alone. Verified 2026-08-28: with DRC-4029 at this stage,
  `status --next` returned it in neither `dispatchable` nor `ready_gates`.

- **Inputs:** The completed `implementation` stage report, and the Linear identifiers it wrote —
  the decision issue filed, or the issue closed and the dependents released.
- **Outputs:**
  - `status: recorded`, and nothing else in frontmatter moved. `verdict` empty, `completed` empty —
    the issue was neither delivered nor rejected, and the binary agrees: an empty verdict "always
    passes", and the verdict gate keys on the finalize action rather than on reaching a stage.
  - The relevant Linear identifier in the entity body, so a later reader follows the chain in one
    hop without re-deriving it.
  - No archive. Archiving is refused while a `merge:` hook has not run, and there is no delivery to
    run it against. Leaving the entity on the board is also the more useful state:
    `spacedock status --where status=recorded` is then the list of cycles that ended in the record.
- **Good:** The Linear identifier is reachable from the entity in one hop, and **Linear — not this
  stage — is what `selection` reads to decide what happens next.** This workflow does not track why
  an entity is here; the issue's own state does.
- **Bad:** Parking here on a hunch that an issue is hard. This stage means a real, checkable change
  landed in Linear — a filed decision issue holding a `blocks` edge, or a closed issue with its
  dependents released. Setting `verdict: REJECTED` to satisfy a guard: it is the one value that
  makes the merge-hook guard stand down, which makes it exactly the tempting lie, and it records a
  judgment on the work that nobody made.

**Closeout sequence**, in this order. Derived on DRC-4029; the ordering is not arbitrary, because
two of the steps trip guards when combined.

1. `status --set {slug} status=recorded` — **alone.** Do not add `worktree=` to this call: clearing
   `worktree` is itself classified a terminal update, so combining them trips the merge-hook guard
   and the whole call refuses.
2. `status --set {slug} worktree= --force` — field-scoped, and the one `--force` this path needs.
   Before using it, prove the guard's premise is false rather than assuming: `pr` empty, `mod-block`
   empty, and the worktree at the trunk tip with zero commits ahead. There was no delivery, so no
   ceremony step was skipped. Clearing is not optional — `recorded` is neither initial, gated nor
   terminal, so a non-empty `worktree` makes the post-dispatch guard demand a
   `## Stage Report: recorded` that will never exist, and the entity could not be moved later.
3. `git worktree remove {path}` then `git branch -d {branch}`. Use `-d`, never `-D`: it refuses if
   the branch carries unmerged work, which is the check, not an inconvenience.
4. `state commit {slug}`.

**What `selection` does with it next**, decided by reading Linear rather than this stage:

| The issue's Linear state | What happens |
|---|---|
| `Blocked` | Left alone. Rule 1 drops it while the `blockedBy` edge is live. |
| `Done` / `Canceled` | Closed. Note it and leave the entity parked; it is the record of the cycle. |
| Open and unblocked | An ordinary candidate again — move the entity `recorded → selection` for a fresh cycle. **Do not file a second entity for the same issue.** |

## Review-finding disposition

Every finding enters this checkpoint when it arrives during implementation, review, a detached
audit, consequential FO quick work, or a correction routed from a rejected gate.

1. The reviewer owns observation, not task ownership or authorization.
2. The worker preserves the finding, investigates without candidate mutation, records the four
   evidence fields, and proposes materiality, task ownership, and disposition separately. Its
   `actor:ensign` round Resolution is advisory.
3. The FO sends a distinct `fix`, `decline`, `hold`, or `route for decision` authorization through
   the runtime's addressable-worker boundary.
4. The reviewer recommends `PASSED` or `REJECTED`; a new finding re-enters step 1.
5. Only the captain changes approved scope, accepted value, thresholds, tolerance, or acceptance
   criteria.
6. After revise is selected, rejection routing transports the evidence, workflow classifications,
   authorized dispositions, and concrete assignment unchanged; it never re-triages.

Before FO authorization, candidate bytes and Git HEAD stay unchanged, no candidate commit is made,
and no reviewer rerun starts. Read-only file/history inspection, non-mutating reproductions,
existing tests, and adversarial work in a throwaway checkout are allowed. After authorization,
perform only that disposition; `hold` and `route for decision` forbid mutation and rerun. Changed
evidence re-enters the checkpoint, and an unobservable runtime authorization means hold and
re-consult.

The four evidence fields are released user and normal workflow; observable harm; affected value AC
or non-negotiable boundary; and trigger evidence. Field 3 uses `value-ac[AC-N]`,
`captain-ruling[YYYY-MM-DD]`, or `contract[repo/relative/path#anchor]` plus a nonblank claim;
`none:` plus a rationale cannot establish Material.

- **Material:** all four fields establish supported-workflow harm to a value AC or protected boundary.
- **Deferred risk:** the trigger is hypothetical, unsupported, unobserved, or outside current
  promises; record its promote-to-material condition. **File it in Linear** rather than promoting it
  into the current PR.
- **Polish:** no current user-visible loss or protected boundary is at risk.
- **Needs decision:** the task cannot own the required scope, product, or compatibility decision.

Materiality and task ownership are independent. Owned Material is eligible for an FO-authorized fix;
out-of-scope Material holds unchanged as Needs decision. Deferred risk or Polish may be declined
only after FO authorization.

After reviewer and worker entries and FO consultation, the First Officer appends the Cycle line
directly from the authorized package. Then the First Officer invokes
`${SPACEDOCK_BIN:-spacedock} gate record --round` with the canonical Briefing/log before reviewer
re-run or next-gate preparation. The neutral recorder retains those bytes and advances
`review-round`; it applies no gate or status change, and it does not parse classifications or
project workflow prose. A correction round uses
`- Cycle {N}: {verdict} — {reviewer/loop}; surface {files}/{LOC} vs estimate {declared} ({P}%); AC {unchanged | narrowed: <note>}`.
Compare `git diff --numstat "$(git merge-base main HEAD)"..HEAD` with the triage estimate; beyond
declared tolerance or on narrowed AC, require a captain-visible design reset. Cycle 3 escalates.

## Post-merge Linear reconcile

Required, and the reason this workflow exists rather than just the skills it calls. Runs when the
merge is detected, before the entity is reported closed to the captain. All five, in order, and
only once the merge to `main` is confirmed.

1. Move the Linear issue to `Done`. Not before the merge.
2. Fix the owning milestone description wherever the merge made it false. Keep the older dated
   section and label it historical rather than deleting it. This write resends the whole
   description and Linear's serializer will move some emphasis boundaries in text you did not
   touch — see the milestone-edit rule in `## Workflow-specific rules`. Report it; do not repair it.
3. Refresh the project overview's "As of" block. Every derived number lives there, so it is one edit.
4. Check the closed issue's `blocks`. Move anything newly free to `Todo`.
5. If the closed issue still blocks something that no longer depends on it, remove the relation and
   add `relatedTo` in its place, so the closed evidence stays reachable from the item it unblocked.
   **Only when the blocked side is still open.** An edge between two closed issues gates nothing and
   is part of the record of what waited on what — removing those turns a satisfied dependency into
   no dependency, which is a different and less true statement.

Then report: issue worked, milestone updated, overview refreshed, what became unblocked, what is next.

The evidence for why this is not optional, as of 2026-08-21: C6 sat behind DEC-2 after a rewrite
removed its need for one, so a 56 risk-adjusted item read as blocked for weeks. E4 and E5 read as
ready to build while needing a security amendment nobody had filed. *Don't be the bottleneck* said
no item had shipped after B3 and B7 both had. DEC-1 closed and kept a `blocks` edge on E7, so a
closed decision was still gating live work. Each was one edit away from being right and nobody made
it, because closing an issue felt like finishing.

## Writing a dispatch checklist

The FO authors the checklist at each dispatch. Two rules, both learned the hard way on 2026-08-28.

**An item must be satisfiable by the worker it is given to.** `spacedock status` refuses to advance
an entity away from an entered worktree stage while its report carries a `FAILED` item, and that
guard sits deliberately before every `--force` bypass. So an item the worker cannot pass parks the
entity, and the only honest exits are a re-dispatch against a corrected criterion or the captain
authorizing an amendment. On DRC-4029 an item required confirming that a milestone's pre-existing
sections were untouched — which `save_milestone` cannot deliver, because it has no patch operation
and resends the whole description. No worker could have passed it.

**An addendum to a stage report must not reuse the `## Stage Report: {stage}` heading.** The report
selector takes the **latest** section matching that prefix and stops, so a second one silently
*replaces* the first rather than supplementing it — the original's items become invisible to
`status --read --checklist` and to the completion guard, and the entity cannot advance. Nest an
addendum as a `###` subsection inside the existing report instead, and give every item an evidence
continuation line on its own line, since an item whose evidence shares its line parses as having
none. Measured 2026-08-28 on DRC-4037, where a correctly-motivated append — preserving the original
report as written, which is the right instinct — hid three fully-evidenced items from the machine.

**Name the artifact, not a category.** An item that says "leave the issue in a state that reflects
X" does not say whether it means the Linear workflow state, a relation, or a body section — and if
another item already owns one of those, the ambiguity is invisible to the author and obvious to the
worker. Name the field, the relation, or the heading. Measured twice: a self-contradicting milestone
draft on DRC-4122, and an under-specified "state" clause on DRC-4037. Both times the worker stopped
and asked rather than picking silently, which is the behaviour to protect — but the cost was mine to
avoid.

**Separate the process obligation from the outcome assertion.** Ask for the obligation, which the
worker controls: *perform the read-back and report every discrepancy.* Do not fold in an outcome the
worker does not control: *and nothing drifted.* A conjunctive item fails whole on any one part, so an
outcome clause turns a correctly-performed check into a `FAILED` and hides the good work inside it.
Discrepancies are dispositioned by the FO under `## Review-finding disposition`; they are not the
worker's to pass or fail.

## Workflow-specific rules

The FO/ensign operating contract already governs generic stage semantics and proof discipline:
prefer the cheapest check that can fail — a shipped guard's run, an existing mechanical check, a
one-off falsifiable exercise recorded in the report, then the captain's judgment — with new standing
enforcement as the last resort; prove by exercising rather than re-reading; and reject any AC whose
only proof is a review of its own prose. The rules below add the specifics of this repository.

- **Linear is the only source of state.** `docs/visibility-2x2/items.json` holds the panel's scores
  and its `state` fields are deliberately stale, kept as the dated record of what was scored. Use it
  for scores, never for what has shipped.
- **One issue per branch.** If a second problem turns up, file it and carry on. Several issues at
  once means several worktrees, which is normal here and has its own failure modes: read **Parallel
  Work** in `AGENTS.md` before starting the second, and hand its contention list to every builder.
  An agent that has not been told will report a loopback-port collision as a regression, and it
  reads convincingly.
- **Never edit a version field.** The tag-driven Release workflow owns them and `version-guard`
  fails any PR that changes one.
- **A milestone edit rewrites the whole description, and Linear's serializer will move some
  emphasis.** Measured 2026-08-28 on DRC-4029's milestone write: `save_milestone` has no patch
  operation, so inserting a section resends the entire existing description, and Linear re-serializes
  it from its document model on the way back. A bold run whose boundary directly touches an inline
  code span or a link gets its mark boundary moved or the run split — five occurrences on that one
  write, three of them in pre-existing text the edit was not touching. Text content was unchanged in
  every case. The trigger is **adjacency**, not the presence of code or links: `` `long` **latches** ``
  has a space between the two, was already canonical, and round-tripped untouched.
  **The space mitigation is weaker than first recorded.** Measured twice on 2026-08-28: a space
  between an emphasis run and a *following* code span did **not** prevent the move — the bold run
  swallowed the space, and an italic run containing a code span came back split at it. Sibling
  bullets whose runs were followed by ordinary text round-tripped clean, so the trigger is **a code
  span following the run**, not adjacency in general. The reliable avoidance is structural: **do not
  end an emphasis run immediately before a code span** — restructure the sentence. **In text you
  author, whichever stage you are in**, that is the guard.

  **The structural avoidance is proven, not theorised.** On the same day, a section authored to keep
  every code span away from every emphasis run round-tripped **byte-identical, zero boundary moves**,
  through the same API that damaged the hard-wrapped draft beside it.

  **And the damage is progressive, which "the boundary moves" understates.** A first write moves the
  boundary, leaving the malformed `**label. **` shape; a *later* write resolves that malformed
  nesting by **dropping the mark entirely**. Measured 2026-08-28 on DRC-4122, where five pre-existing
  lead-ins lost their bold outright — with the visible cost that option B's label is now unbolded
  while A, C and D remain bold, so a closed decision record's option list reads inconsistently. This
  happened through a `patch` **append** op that re-transmitted no existing byte, which is the
  sharpest confirmation yet that a targeted patch is not a targeted write.

  **Repair provably cannot succeed**, measured on both halves of one cycle: sending the clean
  ``**label.** `code` `` returns the damaged ``**label. **`code` ``, so repairing a damaged run
  re-creates the exact input the next write drops. There is no stable state to repair toward. Author
  it correctly the first time or accept the seam. The guard binds the **author**, and `implementation` authors prose too — an `## Outcome`
  section composed from a ruling is authored, not copied. What `implementation` must never do is
  **alter approved prose** to satisfy the guard: a draft the gate approved is immutable, and editing
  it is a second unapproved change to a record other people read. So: apply the guard to what you
  write, write approved drafts verbatim, and report the boundary move either way. This rule has been
  revised three times, each time after a real miss — first written as "expect it", then wrongly
  narrowed to `triage` only, now bound to authorship. **In pre-existing text nobody is touching** it is unavoidable regardless, because the
  whole description is resent.
  There, say so in the stage report and **do not repair it.** A repair cannot succeed, and that is
  measured rather than inferred: the pre-write capture showed all three affected spots already in the
  clean form, the write resent those captured clean bytes verbatim, and they came back shifted. So
  sending clean bytes is precisely what produces the shifted form, and a second write would reproduce
  it — it is not merely *likely* to be a no-op. Nothing is visibly wrong where people read it either,
  since Linear renders from its document model rather than from this markdown. This matters because
  `## Post-merge Linear reconcile` step 2 edits a milestone description on every completed issue.
- **The first `gate prepare` on a flat entity makes it a folder entity.** `prepare` writes the room
  under `{slug}/review/...`, and `status --validate` then warns that a flat `{slug}.md` beside it
  leaves every retained room unreadable. Fix it in one commit —
  `git mv {slug}.md {slug}/index.md` **and** rewrite every `room-ref: ./{slug}/` to `room-ref: ./` —
  and do it while **no worker holds the entity**, because moving the file out from under a running
  agent breaks its writes. The right moment is right after a stage report lands and before the next
  dispatch. What is at stake is the briefing that records a captain's decision, so it is an audit
  trail rather than a tidy-up. Seen on DRC-4029 and again on DRC-4271; expect it every cycle.
- **`save_issue`'s `patch` is not a targeted write either.** Measured 2026-08-28 on DRC-4029: a
  `patch` call re-serialized the whole document and moved emphasis boundaries outside the patched
  range. The milestone rule above is really a Linear-write rule — it applies to every issue and
  milestone body write, however targeted the call looks.
- **Any issue reference in body text becomes a mention, and a mention creates relations.** This is a
  second mechanism, distinct from the serializer, and it does two things: it can drop an adjacent
  bold or italic run, and it **silently adds `relatedTo` edges nobody asked for**. **Markdown links
  do not prevent it** — measured 2026-08-28, when five unrequested edges appeared across two issues
  despite *every* identifier being written as a link, because a link whose href is a Linear issue URL
  is parsed as a mention too. There is therefore no safe way to reference an issue in a body: expect
  relations from any reference, and **read back the relation set after any body write that mentions an issue.**
  It has not been observed creating a `blocks` or `blockedBy` edge; if it ever does, that is Material
  immediately, because rule 1 of the pick order reads exactly those and a silent gate would drop a
  live candidate.
- **Check a Linear error against read-back state before retrying it.** **Reproducible, not a
  one-off** — observed three times across two cycles (2026-08-28): a `save_issue` call returns
  `Error: Failed to remove 1 relation(s)` while every part of it has in fact landed — body patch, state change, `blockedBy` cleared, `relatedTo` added. Adding `relatedTo`
  appears to convert the existing blocking relation, leaving `removeBlockedBy` nothing to remove. A
  retry on the error alone would have been a second unapproved write to a shared record.
- **A milestone correction may go in a comment when there is no capture to script from.**
  `save_milestone` has no patch operation, so any description edit resends the whole body — and the
  rule above requires such an edit be built by script from a pre-write capture with an exactly-once
  assertion and a diff. When the capture exists only in an agent's context rather than on disk,
  hand-reconstructing thousands of words to satisfy a rule about not hand-reconstructing them is the
  wrong trade. A dated comment on the milestone renders with the description, is additive, and
  carries no resend risk. State in the comment why it is a comment.
- **Send Linear bodies unwrapped.** Entity files here are hard-wrapped at 100 columns; Linear reads
  those newlines as hard breaks and re-marks emphasis **per line**, producing split runs and ragged
  mid-sentence breaks the draft never intended. Measured 2026-08-28 on DRC-4037, where a hard-wrapped
  draft produced stray marker artifacts while two unwrapped drafts sent the same day showed none.
  Join paragraphs to one line before sending; the wording does not change.
- **Build a milestone edit by script from a pre-write capture, and diff it before sending.** The
  whole description is resent on every write, so a hand-assembled body is an unbounded diff nobody
  has read. Capture the live description first, apply the authorized replacements programmatically,
  assert each target passage is present **exactly once** before replacing it, and diff the result —
  the hunk count should equal the number of authorized edits and nothing else should move. Adopted
  as the default after DRC-4122's cycle used it and could state "exactly three hunks, no other
  change" as a fact rather than an intention.
- **Verify PR content at the SHA, never from `gh pr diff`.** Measured 2026-08-28 on PR #238: a
  `gh pr diff` grep returned added lines carrying a harness name list that was present in **no**
  version of the file — not the pre-correction head, not the corrected head. It was pre-PR draft text
  the author had already removed, served from a stale view, and it nearly produced a false alarm
  against an accurate review. The authoritative reads are `git show <sha>:<path>` and the contents
  API at that ref, compared by checksum. Use them before contradicting anyone.
- **Write records specific enough to be contradicted, and when a later measurement disagrees with a
  recorded figure, suspect a hidden variable before suspecting a miscount.** DEC-3 recorded a
  `core.fsmonitor` hook running "twice per invocation" **at git 2.55.0**. Two cycles later a build
  re-measured it varying only the hook's exit code: exit 0 gives one invocation, exit 1 gives two,
  because git re-runs a hook that signals failure. **Both figures were right and neither cycle
  miscounted** — but the intervening correction, which the FO authorized, recorded it as a wrong
  figure and misrepresented what had happened. Two lessons, and the second is the one worth keeping.
  The FO had been told the exit-code nuance by an earlier review and still wrote the simpler version;
  simpler was less true. And the discrepancy was **findable at all only because the original record
  named a number and a version** — a hedged note saying the hook "may run more than once" would have
  absorbed it silently and the mechanism would never have been learned. Prefer the falsifiable claim
  to the safe one.
- **Re-baseline the surface estimate at a correction round.** A round's content is the findings, and
  findings are by definition unknown when the estimate is declared — so measuring a post-correction
  branch against a pre-review figure measures how much review found, not how accurate the estimate
  was. Declare the round's own surface separately. Measured on DRC-4037 PR 1, where correction round
  1 came to +414 lines of which roughly **four were functional**: the rest were oracles the review
  had explicitly demanded, because R3's entire finding was that the guards were unpinned and R5's was
  that an acceptance criterion's named oracle did not exist. Trimming to the original tolerance would
  have deleted exactly what the round was routed to add. This is the fix the captain's
  accepted-once caveat asked for, not a way around it.
- **Never mark an issue `Done` before its PR is merged to `main`.**
- **Never widen scope to make an issue feel complete.** The board's estimates assume the narrow
  reading.
- **Repo-mutation worktree layer.** `implementation` and `review` run in a worktree against the
  codebase, and `review` is `fresh` so an agent that did not build the change checks it. PR state
  lives on the `pr` field, managed by the `pr-merge` mod — there is no `pr-open` or `awaiting-merge`
  stage.
- **No prose-grep over instruction files.** A string, substring, or regex match over an instruction
  file the model reads (this README, `AGENTS.md`, a skill) never proves a behavioral claim. The
  matched text was written by the same implementer the check polices, so it asserts only that the
  file contains what we put in it. A valid paraphrase fails it and an inverted clause passes it. To
  settle a case, ask whether the expected value comes from outside the file under test; if it does
  not, the check is a tautology and is banned. A check binding two independent values that can
  diverge — the plugin manifest's version sharing a major.minor with the binary's — is legitimate.
  Prose-greps are one-off validation evidence, never committed tests.
- **Evidence must be able to fail.** Each AC's cited evidence names the concrete change that would
  flip it. An author who cannot name what would make the evidence fail has not shown it can fail,
  and the criterion does not count.
- **Frontend byte pins are the conflict you will get.** `tests/test_next_page.py` holds per-part sizes
  and digests plus the assembled page. Recompute them from the assets rather than resolving a
  conflict textually. Exactly one in-flight PR may touch `cargento_runtime/web/`.
- **A session you spawn leaves daemons behind.** Driving a harness to reproduce something starts
  that harness's own hooks and they outlive the sandbox. Thirteen survived a deleted directory once
  and drove the load average to 18, which caused the contention failures above. Kill what you
  started, and scope the kill to what you started.
- **Test-first authoring.** For a code or fixture deliverable, write the failing test first, watch
  it fail for the right reason, then write the minimum code to pass. The test is what the gate
  judges.
- **Detached adversarial audit** for high-stakes surfaces — a front-door launcher, status or guard
  mutation paths, shipped contract or scaffolding, CI and release machinery. Run a read-only audit
  on a throwaway checkout that tries to refute the review with an edit the deliverable's own tests
  should catch. "Refuted nothing material" is a valid recorded outcome. The audit also fires on AC
  provenance: when an AC's expected value is derived from the same package's production functions
  or constants, run the adversarial-edit check on it — that provenance is the tautology tell.
- **Live scenario for runtime claims.** When an AC's truth is what an agent or model *does* at
  runtime, prove it with a scripted live scenario graded on durable before→after state plus observed
  output, with a negative case that reds the grade. Mark it
  `Verified by: live <ci-run:<id> | session:<path>>`. An offline proxy or a contract-text check
  proves the watcher or the words, never the runtime behavior.

## Workflow State

View the workflow overview:

```bash
spacedock status --workflow-dir docs/roadmap-burndown
```

Output columns: ID, SLUG, STATUS, TITLE, SCORE, SOURCE.

Find dispatchable issues ready for their next stage:

```bash
spacedock status --workflow-dir docs/roadmap-burndown --next
```

### Restoring a fresh clone

Two things in this directory are deliberately **not** in git, and a clone needs both before the
workflow runs.

**The mod.** `_mods/pr-merge.md` is vendored from the Spacedock plugin at install time. Restore it
with:

```bash
mkdir -p docs/roadmap-burndown/_mods
cp "$(dirname "$(dirname "$(command -v spacedock)")")"/../mods/pr-merge.md docs/roadmap-burndown/_mods/ \
  2>/dev/null || cp ~/.claude/plugins/cache/spacedock/spacedock/*/mods/pr-merge.md docs/roadmap-burndown/_mods/
```

It is ignored rather than committed for two reasons, and the second is the load-bearing one. A
committed copy is a fork of the plugin's own file that drifts silently the moment the plugin
updates. And it **fails this repository's documentation gate**: `scripts/validate_plugins.py`
rglobs `docs/**/*.md` and reads the mod's template placeholders — `/{state-owner}/{state-repo}/…` —
as relative links escaping the repository. Editing a file the first officer executes from, in order
to satisfy a linter, is the wrong trade.

**A known divergence follows from that, and it is a papercut worth fixing.** The validator rglobs the
**working tree**, not the git index, so once the mod is restored `python3 scripts/validate_plugins.py`
reports two errors locally against a file that is not in the repository. **CI is unaffected** — it
checks out committed files only, and the mod is not one. But AGENTS.md tells contributors to run that
validator before opening a PR, and a gate that cries wolf locally is one people learn to skip.

The real fix is to move this workflow out of `docs/` entirely — the directory is machinery rather than
documentation, and the validator's `docs/**` rglob is only reaching it because of where it was placed
at commission time. That move touches a linked worktree and a live entity, so it is deliberately not
done here. **Filed as the next housekeeping task on this workflow.** Until then, the honest local
check is to run the validator against a clean export of the committed tree:

```bash
T=$(mktemp -d) && git archive HEAD | tar -x -C "$T" && (cd "$T" && python3 scripts/validate_plugins.py)
```

**The state.** Entity state lives on the `spacedock-state/roadmap-burndown` orphan branch, checked
out as a linked worktree at `docs/roadmap-burndown/.spacedock-state/`. Stage transitions commit there and never
touch the code branch. On a fresh clone, run `spacedock state init` to fetch the branch and re-add
the worktree.

## Issue Template

```yaml
---
id:
title: The Linear issue title, verbatim
status: selection
source: https://linear.app/recce/issue/DRC-XXXX/...
started:
completed:
verdict:
score:
worktree:
issue:
pr:
mod-block:
linear-status:
milestone:
release:
estimate:
reconciled:
---

One line on what this issue is, from Linear. The authoritative body lives in Linear; `triage`
fetches it live and writes the sharpened version back there.

## Problem

{Triage: what is broken or missing, why it matters now, and what a fix must cover — checked against
the current codebase, not restated from the issue.}

## Proposed approach

{Triage: the direction chosen, and the simplest alternative rejected with the reason it cannot
deliver the value.}

## Linear edits made

{Triage, before any Linear write: the original issue body and owning milestone description copied
verbatim, then the drafted rewrite of each. The gate compares them and authorizes the write;
`implementation` performs it as its first action. This section is both the restore point and the
audit trail.}

## Expected surface and tolerance

Estimate: {+NNN} net LOC across {M} files, tolerance {±NN%}.
Semantics this may change: {command grammar, stored formats, authority, runtime behavior, or `none`}.

## Acceptance criteria

Each AC names a property of the finished change (not a stage action) and how it is verified. Mark
each **offline** or **interactive**.

**AC-1 — {End-state property.}** (offline)
Verified by: {test name / command output or exit code / file the change produces / resulting on-disk
state — something outside this entity body that a future reader can reproduce and that can fail.}
Falsified by: {the concrete change that would make this evidence fail.}

## Test plan

{What tests verify the implementation, estimated cost, whether E2E is needed.}

## Review depth

{Review: the depth chosen from AGENTS.md's Calibrating Effort table, and the property of the diff
that justified it.}

### Feedback Cycles

{First officer appends one `- Cycle {N}: ...` line per correction round; the review gate reads
findings from here.}

## Out of scope

{What this issue deliberately does not address.}
```

## Commit Discipline

- Commit status changes at dispatch and merge boundaries
- Commit issue body updates when substantive
- Implementation commits land on the worktree branch, DCO signed off; merge to `main` happens via
  the `pr-merge` mod after the review gate
- Entity state commits land on the state orphan branch, never on the code branch
